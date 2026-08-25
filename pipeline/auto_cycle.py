#!/usr/bin/env python3
"""One automated cycle: PDF CLS → match Medinet (2 TK) → dual-write CLS.

Routing (single path):
  2 TK TTHC + FULL → điền cả 2 → PROCESSED / UNDER 18
  1 TK TTHC + FULL → điền TK đó → TK1 / TK2
  TTHC + PARTIAL / mẫu khác → điền phần có → ERROR
  Trùng tên không phân biệt → UNDER 18
  Không TTHC cả 2 TK → MISSING

Scan:
  --full-scan: TOAN BO folder
  hourly: INBOX_CLS + MISSING CSV rematch + TK1/TK2 CSV rematch
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from medinet_api import (  # noqa: E402
    LAB_TO_FORM,
    authenticate,
    cls_has_lab_values,
    cls_missing_lab_fields,
    cls_urine_incomplete,
    get_cls,
    insert_cls,
    labs_to_form_payload,
    load_cls_view,
    verify_cls_saved,
    web_cls_looks_incomplete,
)
from pdf_extract import classify_pdf_coverage, extract_pdf  # noqa: E402
from phase_b_import import write_result_excel  # noqa: E402
from phase_b_preview import (  # noqa: E402
    build_root,
    load_config,
    load_or_fetch_merged_unit_index,
    resolve_name_year,
    search_patient_live_multi,
)
from tthc_match import (  # noqa: E402
    ACCOUNT_TK1,
    ACCOUNT_TK2,
    account_folder_name,
    accounts_label,
    resolve_tthc_matches,
)
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()

PENDING = {"NEW_LAB", "WAITING_ADMIN", "READY_IMPORT", "ERROR", "ERROR_IMPORT"}
TERMINAL_SKIP = {"IMPORTED", "SKIP_ALREADY_CLS", "PARSE_ERROR"}


def _today_dmy() -> str:
    return date.today().strftime("%d/%m/%Y")


def _drive_dirs(cfg: dict) -> tuple[Path, Path, Path, Path, Path]:
    """Return (sync_root, inbox, processed, error, missing).

    Never fall back to ADMIN repo root — that caused
    ABORT sync=C:\\Users\\thais\\ADMIN after G: died mid full-scan.
    """
    from drive_paths import (
        resolve_g_sync,
        ensure_standard_folders,
        discover_build_root,
        g_pipeline_live,
    )

    # resolve_g_sync: live G: or pinned G: — never ADMIN / D: / C:
    sync = resolve_g_sync(cfg)
    try:
        build = discover_build_root(cfg)
        if g_pipeline_live() is not None:
            ensure_standard_folders(sync, build)
    except Exception as e:
        safe_print(f"WARN ensure folders: {e}")
    inbox = sync / cfg["drive"].get("inbox_folder", "INBOX_CLS")
    processed = sync / cfg["drive"].get("processed_folder", "PROCESSED")
    error_dir = sync / cfg["drive"].get("error_folder", "ERROR")
    missing = sync / cfg["drive"].get("missing_folder", "MISSING")
    return sync, inbox, processed, error_dir, missing


def _collect_scan_dirs(
    sync: Path,
    inbox: Path,
    missing: Path,
    error_dir: Path,
    processed: Path,
    *,
    full_scan: bool,
    repair: bool = False,
    bot_role: str = "all",
) -> list[Path]:
    """Folders whose PDFs are registered + re-queued this run.

    bot_role inbox  → chi INBOX_CLS (+ ERROR khi full/repair)
    bot_role missing → chi MISSING (+ PROCESSED khi full audit)
    bot_role all   → mac dinh cu
    """
    from drive_paths import UNDER18_FOLDER, discover_inbox_dirs

    role = (bot_role or "all").lower()
    inbox_dirs = discover_inbox_dirs(sync, inbox)
    under18 = sync / UNDER18_FOLDER

    if role == "inbox":
        dirs = list(inbox_dirs)
        if full_scan or repair:
            dirs.append(error_dir)
        return _uniq_dirs(dirs)

    if role == "missing":
        dirs = [missing]
        if full_scan:
            dirs.extend([processed, under18])
        return _uniq_dirs([d for d in dirs if d])

    if not full_scan:
        if repair:
            return _uniq_dirs(list(inbox_dirs) + [error_dir, processed, under18])
        return _uniq_dirs(list(inbox_dirs))
    roots: list[Path] = []
    skip = {".git"}
    if sync.exists():
        for child in sorted(sync.iterdir()):
            if child.is_dir() and child.name.lower() not in skip:
                roots.append(child)
    for must in (*inbox_dirs, missing, error_dir, processed, under18):
        if must.exists() and must not in roots:
            roots.append(must)
    return roots


def _uniq_dirs(dirs: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for d in dirs:
        try:
            key = str(d.resolve()).lower()
        except Exception:
            key = str(d).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def _patient_under18(nam_sinh: str, file_name: str = "") -> bool:
    """Age <= 17 by birth year, or child mau M1/M2/M12 in filename."""
    try:
        from move_under18 import is_under18

        return is_under18(nam_sinh=nam_sinh or "", file_name=file_name or "")
    except Exception:
        return False

def _resolve_pdf(row: dict, inbox: Path, *extra_dirs: Path) -> Path | None:
    src = Path(row.get("source_file") or "")
    try:
        if src.exists():
            return src
    except Exception:
        pass
    name = src.name or row.get("file_name") or ""
    if not name:
        return None
    for base in (inbox, *extra_dirs):
        if not base:
            continue
        base_p = Path(base)
        direct = base_p / name
        try:
            if direct.exists():
                return direct
        except Exception:
            pass
        # Never rglob MISSING/PROCESSED (10k+ files hydrates G: Drive).
        if base_p.name.upper() in {"MISSING", "PROCESSED"}:
            continue
        try:
            if not base_p.exists():
                continue
            hits = list(base_p.rglob(name))
        except Exception:
            hits = []
        if hits:
            return hits[0]
    return None


def _move_pdf(pdf: Path, dest_dir: Path, pid: str = "") -> Path | None:
    """Move PDF into dest_dir; return new path or None."""
    if not pdf or not pdf.exists():
        return None
    last_err = None
    for attempt in range(3):
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / pdf.name
            if dest.exists() and dest.resolve() != pdf.resolve():
                dest = dest_dir / f"{pdf.stem}_{pid or 'x'}{pdf.suffix}"
            if dest.resolve() == pdf.resolve():
                return pdf
            shutil.move(str(pdf), str(dest))
            return dest
        except Exception as e:
            last_err = e
            time.sleep(0.4 * (attempt + 1))
    safe_print(f"  MOVE FAIL {pdf.name} -> {dest_dir}: {last_err}")
    return None


def _src_bucket(src: str) -> str:
    u = (src or "").replace("\\", "/").upper()
    if "/UNDER 18/" in u or "/UNDER_18/" in u or u.endswith("/UNDER 18"):
        return "under18"
    if "/INBOX" in u or u.endswith("/INBOX_CLS") or "INBOX_CLS" in u:
        return "inbox"
    if "/MISSING/" in f"/{u}/" or u.endswith("/MISSING"):
        return "missing"
    if "/ERROR/" in f"/{u}/" or u.endswith("/ERROR"):
        return "error"
    if "/TK1/" in f"/{u}/" or u.endswith("/TK1"):
        return "tk1"
    if "/TK2/" in f"/{u}/" or u.endswith("/TK2"):
        return "tk2"
    if "/PROCESSED" in u:
        return "processed"
    return "other"


def counts_from_rows(rows: list[dict]) -> dict[str, int]:
    """Folder counts from tracking CSV (no G: listing)."""
    out = {
        "inbox": 0,
        "missing": 0,
        "error": 0,
        "processed": 0,
        "under18": 0,
        "tk1": 0,
        "tk2": 0,
        "other": 0,
    }
    for r in rows:
        b = _src_bucket(r.get("source_file") or "")
        out[b] = out.get(b, 0) + 1
    return out


def format_counts_line(c: dict[str, int], *, tag: str = "COUNTS") -> str:
    return (
        f"{tag}\tinbox={c.get('inbox', 0)}\tmissing={c.get('missing', 0)}\t"
        f"error={c.get('error', 0)}\tprocessed={c.get('processed', 0)}"
        f"\tunder18={c.get('under18', 0)}"
        f"\ttk1={c.get('tk1', 0)}\ttk2={c.get('tk2', 0)}"
    )


def write_last_counts(build: Path, c: dict[str, int], extra: str = "") -> Path | None:
    try:
        dest = build / "last_counts.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(format_counts_line(c) + (("\n" + extra) if extra else "") + "\n", encoding="utf-8")
        return dest
    except Exception:
        return None


def _row_priority(row: dict) -> int:
    """Lower = import sooner. INBOX first, then ERROR, then MISSING.

    Never tie INBOX with MISSING — extracting 11k MISSING first kills G: Drive
    before any INBOX file is moved (folder counts look unchanged).
    """
    st = (row.get("status") or "").upper()
    src = (row.get("source_file") or "").replace("\\", "/").upper()
    in_inbox = "/INBOX" in src or src.endswith("/INBOX_CLS") or "INBOX_CLS" in src
    in_missing = "/MISSING/" in f"/{src}/" or src.endswith("/MISSING")
    in_error = "/ERROR/" in f"/{src}/" or src.endswith("/ERROR")
    in_processed = "/PROCESSED" in src
    if in_inbox:
        return 0
    if in_error:
        return 1
    if in_missing:
        return 2
    if st == "WAITING_ADMIN":
        return 5
    if in_processed:
        return 6
    if st in {"IMPORTED", "SKIP_ALREADY_CLS"}:
        return 7
    return 4


def _route_after_import(
    *,
    pdf: Path,
    row: dict,
    pid: str,
    coverage: str,
    processed: Path,
    error_dir: Path,
    under18_dir: Path,
    stats: Counter,
    note: str,
    moves: list[str],
    nam_sinh: str = "",
    tk1_dir: Path | None = None,
    tk2_dir: Path | None = None,
    n_accounts: int = 1,
    primary_account: str = "",
    sample_kind: str = "BLOOD_URINE",
    force_error: bool = False,
) -> None:
    """FULL+2TK → PROCESSED/U18; FULL+1TK → TK1/TK2; PARTIAL/OTHER → ERROR."""
    is_kid = _patient_under18(nam_sinh or row.get("nam_sinh") or "", pdf.name)
    other_sample = sample_kind == "OTHER" or force_error
    if other_sample or coverage not in {"FULL"}:
        dest = error_dir
        row["status"] = "ERROR_IMPORT"
        row["notes"] = f"imported_{coverage.lower()}_to_error:{note}"[:200]
        stats["imported_partial_to_error"] += 1
        stats["routed_error"] += 1
        tag = "ERROR"
    elif n_accounts >= 2:
        if is_kid:
            dest = under18_dir
            tag = "UNDER18"
            stats["routed_under18"] += 1
        else:
            dest = processed
            tag = "PROCESSED"
            stats["routed_processed"] += 1
        row["status"] = "IMPORTED"
        row["notes"] = f"imported_full_dual:{note}"[:200]
        stats["imported"] += 1
    else:
        # 1 TK FULL → TK1 or TK2 archive
        folder = account_folder_name(primary_account or ACCOUNT_TK1)
        if folder == "TK2" and tk2_dir is not None:
            dest = tk2_dir
            tag = "TK2"
            stats["routed_tk2"] += 1
        else:
            dest = tk1_dir if tk1_dir is not None else processed
            tag = "TK1"
            stats["routed_tk1"] += 1
        row["status"] = "IMPORTED"
        row["notes"] = f"imported_full_{tag.lower()}:{note}"[:200]
        stats["imported"] += 1
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    moved = _move_pdf(pdf, dest, pid=pid)
    if moved:
        row["source_file"] = str(moved)
        row["file_name"] = moved.name
        moves.append(f"{tag}\t{row.get('ho_ten')}\t{pdf.name}\t->\t{dest.name}/{moved.name}")
    elif pdf.exists():
        row["notes"] = f"{row['notes']};move_failed"[:200]
        moves.append(f"{tag}_MOVE_FAIL\t{row.get('ho_ten')}\t{pdf.name}\t->\t{dest.name}")
    safe_print(
        f"  {tag} coverage={coverage} accounts={n_accounts} kid={is_kid} "
        f"{row.get('ho_ten')} pid={pid}"
    )


def _route_pdf_review(
    *,
    pdf: Path,
    row: dict,
    under18_dir: Path,
    stats: Counter,
    moves: list[str],
    note: str,
    status: str = "PARSE_ERROR",
) -> None:
    """Park PDF in UNDER 18 for manual review (loi PDF / thieu nam sinh)."""
    row["status"] = status
    row["notes"] = note[:200]
    try:
        under18_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    moved = _move_pdf(pdf, under18_dir)
    if moved:
        row["source_file"] = str(moved)
        row["file_name"] = moved.name
        stats["routed_review_u18"] += 1
        moves.append(
            f"REVIEW_U18\t{row.get('ho_ten') or ''}\t{pdf.name}\t->\tUNDER 18/{moved.name}"
        )
        safe_print(f"  REVIEW_U18 {note} {row.get('ho_ten') or pdf.name}")
    else:
        stats["review_u18_move_fail"] += 1


def run_auto_cycle(
    *,
    dry_run: bool = False,
    limit: int = 0,
    force: bool = False,
    repair: bool = False,
    full_scan: bool = False,
    audit_processed: bool = False,
    missing_budget: int = -1,
    sleep_s: float = 0.05,
    bot_role: str = "all",
) -> dict:
    """Process PDFs. bot_role: all | inbox | missing (2 bot song song)."""
    from single_instance import acquire_lock, release_lock

    role = (bot_role or "all").lower()
    if role not in {"all", "inbox", "missing"}:
        role = "all"
    lock_name = "auto_cycle" if role == "all" else f"auto_cycle_{role}"
    lock = acquire_lock(lock_name)
    if lock is None:
        safe_print(f"ABORT: da co bot {role} khac dang chay (locks/{lock_name}.lock).")
        if role == "all":
            safe_print("Chi 1 cua so! Dong bot thu 2 (ghi de cases.csv, DELTA=0 / sai so).")
        return {"abort": "another_instance_running", "bot_role": role}
    try:
        return _run_auto_cycle_inner(
            dry_run=dry_run,
            limit=limit,
            force=force,
            repair=repair,
            full_scan=full_scan,
            audit_processed=audit_processed,
            missing_budget=missing_budget,
            sleep_s=sleep_s,
            bot_role=role,
        )
    finally:
        release_lock(lock)


def _run_auto_cycle_inner(
    *,
    dry_run: bool = False,
    limit: int = 0,
    force: bool = False,
    repair: bool = False,
    full_scan: bool = False,
    audit_processed: bool = False,
    missing_budget: int = -1,
    sleep_s: float = 0.05,
    bot_role: str = "all",
) -> dict:
    """Process PDFs. Hourly = INBOX+MISSING; full_scan = TOAN BO (ke ca PROCESSED)."""
    cfg = load_config()
    build = build_root(cfg)
    sync, inbox, processed, error_dir, missing = _drive_dirs(cfg)

    from drive_paths import g_pipeline_live, is_non_g_pipeline, local_work_build, require_g_on_windows

    build = local_work_build()
    if is_non_g_pipeline(sync):
        safe_print(f"ABORT: o D: mirror may B — chi may A G:. sync={sync}")
        return {"abort": "d_drive_forbidden", "sync": str(sync)}
    if sys.platform.startswith("win") and not require_g_on_windows(sync):
        safe_print(f"ABORT: chi G:\\Drive cua toi\\PKDK_Thuankieu_Pipeline (may A). sync={sync}")
        return {"abort": "not_g_drive", "sync": str(sync)}
    if sys.platform.startswith("win") and g_pipeline_live() is None:
        safe_print("ABORT: G:\\Drive cua toi\\PKDK_Thuankieu_Pipeline chua mount (may A).")
        safe_print("Mo Google Drive Desktop, doi G: hien lai. Khong dung may B / o D:.")
        return {"abort": "g_drive_missing", "sync": str(sync)}

    # Only mkdir after G: confirmed live — never create under ADMIN fallback
    from drive_paths import UNDER18_FOLDER, migrate_stray_inbox

    under18_dir = sync / UNDER18_FOLDER
    tk1_dir = sync / "TK1"
    tk2_dir = sync / "TK2"
    for p in (inbox, processed, error_dir, missing, under18_dir, tk1_dir, tk2_dir):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            safe_print(f"ABORT: khong tao folder tren G: ({e}). sync={sync}")
            return {"abort": "g_mkdir_failed", "sync": str(sync)}
    try:
        n_mig = migrate_stray_inbox(sync)
        if n_mig:
            safe_print(f"MIGRATE stray inbox -> INBOX_CLS: {n_mig} pdfs")
    except Exception as e:
        safe_print(f"WARN migrate inbox: {e}")

    # Plan MISSING rematch budget early (TTHC often added after park in MISSING)
    role = (bot_role or "all").lower()
    if role == "inbox":
        missing_budget = 0
    elif role == "missing" and missing_budget < 0:
        missing_budget = 2500
    if missing_budget < 0:
        if full_scan:
            mb_plan = 100000
        elif repair:
            mb_plan = 0
        else:
            mb_plan = 1500
    else:
        mb_plan = int(missing_budget)
    missing_budget = mb_plan
    rematch_missing_left = mb_plan
    missing_left = mb_plan
    # TK1/TK2 rematch when opposite account gets TTHC later (CSV only)
    rematch_tk_budget = 0 if role == "inbox" else (800 if not full_scan and not repair else 0)
    rematch_tk_left = rematch_tk_budget

    # full-scan: audit PROCESSED — chi bot missing/all (inbox khong audit)
    if full_scan and role != "inbox":
        audit_processed = True
    elif role == "inbox":
        audit_processed = False

    mode = "FULL_SCAN" if full_scan else ("REPAIR" if repair else "HOURLY")
    if role != "all":
        mode = f"{mode}_{role.upper()}"
    scan_dirs = _collect_scan_dirs(
        sync,
        inbox,
        missing,
        error_dir,
        processed,
        full_scan=full_scan,
        repair=repair,
        bot_role=role,
    )
    safe_print(f"Mode: {mode} | bot={role} | scan dirs ({len(scan_dirs)}): {[d.name for d in scan_dirs]}")
    safe_print(f"MISSING rematch budget this run: {missing_budget} | TK1/TK2 CSV: {rematch_tk_budget}")
    safe_print(
        "Match TTHC: ho+ten DAY DU + nam/ngay sinh/SDT/CCCD "
        "(thieu OK neu khong conflict) | dual-write 2 TK"
    )
    safe_print(
        "Route: 2TK+FULL->PROCESSED/U18 | 1TK+FULL->TK1/TK2 | "
        "PARTIAL/OTHER->ERROR | noTTHC->MISSING | trung ten->UNDER18"
    )
    cases_path = ROOT / cfg.get("tracking", {}).get("cases_csv", "tracking/cases.csv")
    from hourly_sync import read_cases, register_new_files, write_cases  # local import

    rows = read_cases(cases_path)
    counts0 = counts_from_rows(rows)
    safe_print(format_counts_line(counts0, tag="COUNTS_BEFORE"))
    write_last_counts(build, counts0, extra="phase=before")
    added = 0
    added_err = 0
    added_missing = 0
    for d in scan_dirs:
        n = register_new_files(d, rows)
        added += n
        tag = d.name.upper()
        if tag == "ERROR":
            added_err += n
        elif tag == "MISSING":
            added_missing += n

    # CRITICAL: every PDF physically in scan dirs must be re-queued each run.
    # Tracking often says WAITING_ADMIN / SKIP / IMPORTED while file still sits
    # in INBOX/MISSING → hourly then reports "0 patients" and keeps missing them.
    by_name = {}
    by_hash = {r.get("file_hash"): r for r in rows if r.get("file_hash")}

    def _base_name(name: str) -> str:
        return re.sub(r"_\d{5,7}(?=\.pdf$)", "", name, flags=re.I).lower()

    for r in rows:
        for cand in (
            Path(r.get("source_file") or "").name,
            r.get("file_name") or "",
        ):
            if not cand:
                continue
            by_name.setdefault(cand.lower(), r)
            by_name.setdefault(_base_name(cand), r)

    requeued_disk = 0
    orphan_registered = 0
    for base in scan_dirs:
        if not base.exists():
            continue
        tag = base.name.lower()
        for pdf in base.rglob("*.pdf"):
            key = pdf.name.lower()
            r = by_name.get(key) or by_name.get(_base_name(pdf.name))
            if r is None:
                # Hash may already exist under another path — retarget that row
                try:
                    from hourly_sync import sha256_file

                    digest = sha256_file(pdf)
                except Exception:
                    digest = ""
                r = by_hash.get(digest) if digest else None
                if r is None:
                    hints = {}
                    try:
                        from hourly_sync import parse_filename_hints

                        hints = parse_filename_hints(pdf.name)
                    except Exception:
                        pass
                    r = {
                        "case_key": hints.get("ma_phieu") or (digest[:16] if digest else pdf.stem[:16]),
                        "source_file": str(pdf),
                        "file_hash": digest,
                        "ho_ten": hints.get("ho_ten", ""),
                        "cccd": "",
                        "ngay_kham": hints.get("ngay_kham", ""),
                        "mau_kham": hints.get("mau_kham", ""),
                        "ma_phieu": hints.get("ma_phieu", ""),
                        "has_lab_file": "YES",
                        "has_admin_info": "",
                        "status": "READY_IMPORT",
                        "import_attempts": "0",
                        "last_checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "imported_at": "",
                        "notes": f"orphan_{tag}_registered",
                    }
                    rows.append(r)
                    if digest:
                        by_hash[digest] = r
                    orphan_registered += 1
                by_name[key] = r
            old = (r.get("status") or "").upper()
            r["source_file"] = str(pdf)
            r["file_name"] = pdf.name
            # full-scan: ép rematch TTHC (rule mới) cho mọi PDF kể cả đã IMPORTED
            # hourly: giữ IMPORTED/SKIP trên disk để tránh quét lại không cần
            if full_scan:
                if old != "READY_IMPORT" or f"disk_{tag}_fullrematch" not in str(r.get("notes") or ""):
                    r["status"] = "READY_IMPORT"
                    r["import_attempts"] = "0"
                    r["notes"] = f"disk_{tag}_fullrematch:{old}"[:200]
                    requeued_disk += 1
            elif (not full_scan) and tag == "missing" and old in {"WAITING_ADMIN", "READY_IMPORT", "NEW_LAB"}:
                # Rematch MISSING: many already have TTHC on Medinet now.
                # Cap by rematch_missing_left so G: Drive stays mounted.
                if rematch_missing_left > 0:
                    r["status"] = "READY_IMPORT"
                    r["import_attempts"] = "0"
                    r["notes"] = f"disk_missing_rematch:{old}"[:200]
                    requeued_disk += 1
                    rematch_missing_left -= 1
                else:
                    r["status"] = "WAITING_ADMIN"
            elif old in {"IMPORTED", "SKIP_ALREADY_CLS"}:
                if (r.get("notes") or "") != f"disk_{tag}_done:{old}":
                    r["status"] = old
                    r["import_attempts"] = "0"
                    r["notes"] = f"disk_{tag}_done:{old}"[:200]
                    requeued_disk += 1
            elif old != "READY_IMPORT" or f"disk_{tag}_requeue" not in str(r.get("notes") or ""):
                r["status"] = "READY_IMPORT"
                r["import_attempts"] = "0"
                r["notes"] = f"disk_{tag}_requeue:{old}"[:200]
                requeued_disk += 1
    if orphan_registered:
        safe_print(f"Registered orphan PDFs on disk: {orphan_registered}")
    if requeued_disk:
        safe_print(f"Re-queued from disk scan dirs: {requeued_disk}")

    # Rematch MISSING from tracking CSV — do NOT list 10k files on G:.
    # Oldest last_checked first so 8 rounds of 2500 rotate through the backlog.
    csv_missing_queued = 0
    csv_missing_total = 0
    if role in {"all", "missing"} and (not full_scan) and (not repair) and missing_budget > 0:
        miss_rows = []
        for r in rows:
            src_u = (r.get("source_file") or "").replace("\\", "/").upper()
            if "/UNDER 18/" in src_u or "/UNDER_18/" in src_u:
                continue
            if "/MISSING/" in src_u or src_u.endswith("/MISSING"):
                miss_rows.append(r)
        csv_missing_total = len(miss_rows)
        miss_rows.sort(
            key=lambda r: (
                r.get("last_checked_at") or "",
                r.get("file_name") or r.get("source_file") or "",
            )
        )
        for r in miss_rows:
            if rematch_missing_left <= 0:
                break
            old = (r.get("status") or "").upper()
            if old not in {"WAITING_ADMIN", "READY_IMPORT", "NEW_LAB", "PARSE_ERROR"}:
                continue
            fname = Path(r.get("source_file") or "").name or r.get("file_name") or ""
            _, year = resolve_name_year(
                {
                    "ho_ten": r.get("ho_ten") or "",
                    "nam_sinh": r.get("nam_sinh") or "",
                    "file_name": fname,
                    "source_file": r.get("source_file") or "",
                }
            )
            # Under-18 in MISSING still rematch (M2 form) — do not skip
            r["status"] = "READY_IMPORT"
            r["import_attempts"] = "0"
            r["notes"] = f"csv_missing_rematch:{old}"[:200]
            rematch_missing_left -= 1
            csv_missing_queued += 1
        safe_print(
            f"MISSING rematch from CSV (no G: walk): queued={csv_missing_queued} "
            f"tracked={csv_missing_total} budget={missing_budget}"
        )

    # Rematch TK1/TK2 from CSV when opposite account later gets TTHC
    csv_tk_queued = 0
    if role in {"all", "missing"} and rematch_tk_budget > 0:
        tk_rows = []
        for r in rows:
            src_u = (r.get("source_file") or "").replace("\\", "/").upper()
            if "/TK1/" in f"/{src_u}/" or src_u.endswith("/TK1"):
                tk_rows.append(r)
            elif "/TK2/" in f"/{src_u}/" or src_u.endswith("/TK2"):
                tk_rows.append(r)
        tk_rows.sort(
            key=lambda r: (
                r.get("last_checked_at") or "",
                r.get("file_name") or r.get("source_file") or "",
            )
        )
        for r in tk_rows:
            if rematch_tk_left <= 0:
                break
            old = (r.get("status") or "").upper()
            if old not in {"IMPORTED", "SKIP_ALREADY_CLS", "READY_IMPORT", "WAITING_ADMIN"}:
                continue
            r["status"] = "READY_IMPORT"
            r["import_attempts"] = "0"
            r["notes"] = f"csv_tk12_rematch:{old}"[:200]
            rematch_tk_left -= 1
            csv_tk_queued += 1
        safe_print(
            f"TK1/TK2 rematch from CSV: queued={csv_tk_queued} budget={rematch_tk_budget}"
        )

    requeued_err = 0
    for r in rows:
        src = (r.get("source_file") or "").replace("\\", "/")
        st = (r.get("status") or "").upper()
        in_error = ("/ERROR/" in f"/{src}/") or src.upper().endswith("\\ERROR") or "/ERROR" in src.upper()
        if added_err and (r.get("notes") or "") == "registered_from_inbox" and "ERROR" in src.upper():
            r["notes"] = "registered_from_error"
            r["status"] = "READY_IMPORT"
            r["import_attempts"] = "0"
            requeued_err += 1
        elif repair and in_error:
            # PDF still in ERROR → always re-import (full-scan/repair catches old gaps)
            r["status"] = "READY_IMPORT"
            r["import_attempts"] = "0"
            r["notes"] = f"requeue_error_folder:{st}:{r.get('notes') or ''}"[:200]
            requeued_err += 1
        elif repair and st in {"ERROR_IMPORT", "ERROR"}:
            r["status"] = "READY_IMPORT"
            r["import_attempts"] = "0"
            r["notes"] = f"requeue_error:{r.get('notes') or ''}"[:200]
            requeued_err += 1
        elif repair and st == "PARSE_ERROR":
            r["notes"] = f"requeue_parse:{r.get('notes') or ''}"[:200]
    if requeued_err:
        safe_print(f"Re-queued from ERROR / failed status: {requeued_err}")

    from drive_paths import count_pdfs_fast

    inbox_pdf_n = count_pdfs_fast(inbox) if inbox.exists() else 0
    error_pdf_n = count_pdfs_fast(error_dir) if error_dir.exists() else 0
    missing_pdf_n = counts0.get("missing", csv_missing_total)
    processed_pdf_n = counts0.get("processed", 0)
    safe_print(f"SYNC ROOT: {sync}")
    safe_print(f"Inbox disk: {inbox} (pdfs={inbox_pdf_n}) csv={counts0.get('inbox', 0)}")
    safe_print(f"Missing csv: {missing_pdf_n} (khong list 10k G:; so nay giam khi rematch xong)")
    safe_print(f"Error disk: {error_dir} (pdfs={error_pdf_n}) csv={counts0.get('error', 0)}")
    safe_print(f"Processed csv: {processed_pdf_n}")
    if inbox_pdf_n + error_pdf_n == 0 and missing_pdf_n == 0:
        safe_print("WARN: 0 PDF inbox/error and 0 MISSING in tracking.")

    safe_print(f"Logs (local, not G:): {build}")
    safe_print(
        f"INBOX-first | missing_extract_budget={missing_budget} "
        f"(INBOX+ERROR unlimited; MISSING rematch capped so G: stays mounted)"
    )
    safe_print(
        f"New files registered: {added} total "
        f"(missing_folder={added_missing}, error={added_err})"
    )

    max_per_run = int(cfg.get("import_rules", {}).get("max_imports_per_run", 80))
    if full_scan or repair:
        max_per_run = max(max_per_run, 5000)  # bat so BN cu — khong gioi han thap
    else:
        # Hourly/GAP: drain INBOX + rematched MISSING
        max_per_run = max(max_per_run, 2000)
    if limit:
        max_per_run = min(max_per_run, limit)
    # Reserve most slots for new/empty imports; only a few incomplete overwrites
    max_incomplete = int(cfg.get("import_rules", {}).get("max_incomplete_per_run", 200 if repair else 40))
    if full_scan or repair:
        max_incomplete = max(max_incomplete, 2000)

    from medinet_creds import get_medinet_accounts

    accounts = get_medinet_accounts(cfg)
    safe_print(
        f"Medinet accounts: {accounts[0]['id']} + {accounts[1]['id']} (merged TTHC index)"
    )
    tokens: dict[str, str] = {}
    for acct in accounts:
        tokens[acct["id"]] = authenticate(acct["user"], acct["password"])

    def reauth_acct(aid: str) -> str:
        for acct in accounts:
            if acct["id"] == aid:
                tokens[aid] = authenticate(acct["user"], acct["password"])
                return tokens[aid]
        tokens[accounts[0]["id"]] = authenticate(
            accounts[0]["user"], accounts[0]["password"]
        )
        return tokens[accounts[0]["id"]]

    def account_for(rec: dict | None) -> str:
        if rec and rec.get("_medinet_account"):
            return str(rec["_medinet_account"])
        return accounts[0]["id"]

    def token_for(rec: dict | None) -> str:
        aid = account_for(rec)
        return tokens.get(aid) or tokens[accounts[0]["id"]]

    def make_reauth(rec: dict | None):
        aid = account_for(rec)

        def _r():
            return reauth_acct(aid)

        return _r

    date_from = cfg.get("medinet", {}).get("date_from") or "01/07/2026"
    # date_to empty / missing / stale → always hôm nay (rolling)
    date_to = (cfg.get("medinet", {}).get("date_to") or "").strip() or _today_dmy()
    safe_print(f"Indexing Medinet NgayKham {date_from} -> {date_to} (rolling today) ...")
    cache_dir = ROOT / "pipeline" / "work" / "index_cache"
    # Fresh index when rematching MISSING — TTHC often entered after last cache
    # Rematch: reuse index up to 3h (rounds 2-8). Force rebuild only on full-scan
    # or first rematch after cache miss. Old force-every-round wasted 10+ min/vong.
    if full_scan:
        index_max_age = 0.0
        safe_print("Index: FORCE REFRESH (full-scan)")
    elif missing_budget > 0:
        index_max_age = 3.0
        safe_print("Index: rematch — reuse cache <=3h (M2/M3/M4/M11)")
    else:
        index_max_age = 2.0
    index = load_or_fetch_merged_unit_index(
        accounts,
        date_from,
        date_to,
        cache_dir=cache_dir,
        max_age_hours=index_max_age,
    )
    for acct in accounts:
        tokens[acct["id"]] = authenticate(acct["user"], acct["password"])

    stats = Counter()
    results = []
    unmatched_lines = []
    moves: list[str] = []
    imported_n = 0
    incomplete_n = 0
    flush_every = 25
    from claim_registry import claim_owner, release_claim, release_owner, try_claim

    owner_tag = claim_owner(role)

    def _flush_cases() -> None:
        from single_instance import save_cases_merged

        try:
            save_cases_merged(cases_path, rows, write_cases)
        except Exception as e:
            safe_print(f"WARN flush cases: {e}")

    # PROCESSED rematch happens in the main loop when full_scan=True.
    # The old extra audit_processed pass re-parsed every PDF (and live-searched
    # misses) BEFORE any import — hours of duplicate work on large PROCESSED.
    if audit_processed and not full_scan and processed.exists():
        safe_print("==== AUDIT PROCESSED (no TTHC → MISSING) ====")
        proc_pdfs = sorted(processed.rglob("*.pdf"))
        if limit:
            proc_pdfs = proc_pdfs[:limit]
        for i, pdf in enumerate(proc_pdfs, 1):
            try:
                data = extract_pdf(pdf)
            except Exception as e:
                stats["audit_parse_error"] += 1
                continue
            if not data.get("parse_ok"):
                stats["audit_parse_error"] += 1
                continue
            tthc_a = resolve_tthc_matches(data, index, accounts=accounts)
            if tthc_a.status == "WAITING_ADMIN":
                live_st, live_rec, live_acct = search_patient_live_multi(
                    accounts,
                    tokens,
                    name=str(data.get("ho_ten") or ""),
                    year=str(data.get("nam_sinh") or ""),
                    date_from=date_from,
                    date_to=date_to,
                    ngay_co_kq=str(data.get("ngay_co_kq") or ""),
                    gioi_tinh=str(data.get("gioi_tinh") or ""),
                    sdt=str(data.get("sdt") or ""),
                )
                if live_st != "WAITING_ADMIN" and live_rec:
                    live_rec["_medinet_account"] = live_acct
                    tthc_a = resolve_tthc_matches(
                        data,
                        {
                            "by_fold_year": {
                                f"x|{data.get('nam_sinh') or 'x'}": [live_rec]
                            },
                            "by_name_year": {},
                        },
                        accounts=accounts,
                    )
                    if tthc_a.status != "READY_IMPORT":
                        from tthc_match import TTHCMatchResult

                        tthc_a = TTHCMatchResult(
                            "READY_IMPORT", [live_rec], "audit_live"
                        )
            if tthc_a.status != "READY_IMPORT" or not tthc_a.matches:
                unmatched_lines.append(
                    f"NO_TTHC_FROM_PROCESSED\t{data.get('ho_ten')}\t"
                    f"year={data.get('nam_sinh')}\tngay_kq={data.get('ngay_co_kq')}\t{pdf.name}"
                )
                if not dry_run:
                    moved = _move_pdf(pdf, missing)
                    if moved:
                        stats["audit_moved_missing"] += 1
                else:
                    stats["audit_would_move_missing"] += 1
            else:
                stats["audit_ok"] += 1
            if i % 200 == 0:
                safe_print(f"  audited {i}/{len(proc_pdfs)} ...")
        safe_print(
            f"Audit done: ok={stats['audit_ok']} moved_missing={stats['audit_moved_missing']} "
            f"parse_err={stats['audit_parse_error']}"
        )

    def _release_pdf_claim(key: str) -> None:
        if key:
            release_claim("pdf", key, owner_tag)

    # Process INBOX / READY first, then WAITING_ADMIN, then incomplete repair last
    row_order = sorted(range(len(rows)), key=lambda i: (_row_priority(rows[i]), i))
    safe_print(
        f"Priority queue: inbox/ready first; max_import={max_per_run} max_incomplete={max_incomplete}"
    )

    for ri in row_order:
        row = rows[ri]
        status = (row.get("status") or "").upper()
        file_key = ""

        # Attach file early — always re-check PDFs in current scan dirs
        pdf = _resolve_pdf(row, inbox, missing, processed, error_dir, under18_dir)
        if not pdf or not pdf.exists():
            if status in PENDING | {"IMPORTED", "SKIP_ALREADY_CLS", "PARSE_ERROR"}:
                row["notes"] = "source_pdf_missing"
                stats["missing_pdf"] += 1
            continue
        row["file_name"] = pdf.name
        row["source_file"] = str(pdf)
        src_u = str(pdf).replace("\\", "/").upper()
        in_inbox = ("/INBOX" in src_u) or src_u.endswith("/INBOX_CLS") or "INBOX_CLS" in src_u

        # INBOX trùng tên với folder khác → giữ tạm ở thư mục gốc pipeline
        if in_inbox and not full_scan and not repair:
            try:
                _pdf_check = Path(__file__).resolve().parent / "pdf_check"
                if str(_pdf_check) not in sys.path:
                    sys.path.insert(0, str(_pdf_check))
                from dedup import hold_inbox_duplicate_at_root, inbox_duplicate_exists  # noqa: E402

                if inbox_duplicate_exists(sync, pdf.name, exclude=pdf):
                    if dry_run:
                        safe_print(f"  INBOX_DUP_HOLD_ROOT (dry) {pdf.name}")
                        stats["inbox_dup_hold_root"] += 1
                        continue
                    moved_root = hold_inbox_duplicate_at_root(pdf, sync, dry_run=False)
                    if moved_root:
                        row["source_file"] = str(moved_root)
                        row["file_name"] = moved_root.name
                        row["notes"] = "inbox_dup_hold_root"[:200]
                        stats["inbox_dup_hold_root"] += 1
                        safe_print(f"  INBOX_DUP_HOLD_ROOT {pdf.name} -> {moved_root}")
                    continue
            except Exception as e:
                safe_print(f"  WARN inbox_dup_check: {e}")

        in_missing = "/MISSING/" in f"/{src_u}/" or src_u.endswith("/MISSING")
        in_error = "/ERROR/" in f"/{src_u}/" or src_u.endswith("/ERROR")
        in_processed = "/PROCESSED" in src_u
        in_under18 = (
            "/UNDER 18/" in src_u or "/UNDER_18/" in src_u or src_u.endswith("/UNDER 18")
        )
        in_tk1 = "/TK1/" in f"/{src_u}/" or src_u.endswith("/TK1")
        in_tk2 = "/TK2/" in f"/{src_u}/" or src_u.endswith("/TK2")
        if role == "inbox" and not (in_inbox or ((full_scan or repair) and in_error)):
            stats["skipped_bot_role"] += 1
            continue
        if role == "missing" and not (
            in_missing
            or in_tk1
            or in_tk2
            or (full_scan and (in_processed or in_under18))
        ):
            stats["skipped_bot_role"] += 1
            continue
        # UNDER 18: hourly skip (da import). Full/repair: kiem urea lai.
        if in_under18 and not full_scan and not repair:
            stats["skipped_under18"] += 1
            continue
        # Hourly: INBOX + MISSING + TK1/TK2 CSV rematch. Full-scan: moi folder.
        if not full_scan and not repair and not (
            ("/INBOX" in src_u) or ("/MISSING" in src_u) or in_tk1 or in_tk2
        ):
            continue
        if not full_scan and repair and not (
            ("/INBOX" in src_u)
            or ("/ERROR" in src_u)
            or ("/PROCESSED" in src_u)
            or in_under18
        ):
            continue
        if (not full_scan) and ("/MISSING" in src_u):
            if missing_left <= 0:
                stats["skipped_missing_budget"] += 1
                continue
            missing_left -= 1
            attempted = missing_budget - missing_left
            if attempted == 1 or attempted % 25 == 0:
                safe_print(
                    f"  rematch MISSING {attempted}/{missing_budget} {row.get('ho_ten') or pdf.name}"
                )
        stuck_in_work = (
            full_scan
            or ("/INBOX" in src_u)
            or ("/MISSING" in src_u)
            or ("/ERROR" in src_u)
            or ("/TK1" in src_u)
            or ("/TK2" in src_u)
        )

        # Done rows in work folders must still be re-checked against the current
        # web form first. If fields are complete (Ure ignored), later logic will
        # move them to PROCESSED; if fields are missing, later logic will repair.

        if status == "PARSE_ERROR" and not repair and not stuck_in_work:
            stats["skipped_parse"] += 1
            continue

        # Hourly: recheck INBOX/MISSING/TK1/TK2. Skip IMPORTED only in PROCESSED.
        if status in {"IMPORTED", "SKIP_ALREADY_CLS"} and not repair and not stuck_in_work:
            notes_peek = str(row.get("notes") or "")
            needs_recheck = any(
                x in notes_peek
                for x in (
                    "incomplete",
                    "SET-no-urine",
                    "SET-urine-all",
                    "import_fail",
                    "queued_max",
                    "disk_",
                    "csv_tk12",
                )
            )
            if not needs_recheck:
                stats["skipped_imported" if status == "IMPORTED" else "skipped_already"] += 1
                continue
        if status not in PENDING | {"IMPORTED", "SKIP_ALREADY_CLS", "PARSE_ERROR"}:
            continue

        file_key = str(row.get("file_hash") or pdf.name)
        if not try_claim("pdf", file_key, owner_tag):
            stats["skipped_claim"] += 1
            continue

        try:
            data = extract_pdf(pdf)
        except Exception as e:
            row["status"] = "PARSE_ERROR"
            row["notes"] = f"parse:{e}"[:200]
            stats["parse_error"] += 1
            _route_pdf_review(
                pdf=pdf,
                row=row,
                under18_dir=under18_dir,
                stats=stats,
                moves=moves,
                note=f"parse_exception:{e}"[:120],
                status="PARSE_ERROR",
            )
            _release_pdf_claim(file_key)
            continue

        if not data.get("parse_ok"):
            row["status"] = "PARSE_ERROR"
            row["ho_ten"] = row.get("ho_ten") or data.get("ho_ten") or ""
            row["notes"] = "parse_ok=false"
            stats["parse_error"] += 1
            _route_pdf_review(
                pdf=pdf,
                row=row,
                under18_dir=under18_dir,
                stats=stats,
                moves=moves,
                note="parse_ok=false",
                status="PARSE_ERROR",
            )
            _release_pdf_claim(file_key)
            continue

        row["ho_ten"] = data.get("ho_ten") or row.get("ho_ten") or ""
        row["mau_kham"] = data.get("mau_kham") or row.get("mau_kham") or ""
        data["file_name"] = pdf.name
        data["source_file"] = str(pdf)
        if row.get("ma_phieu"):
            data["ma_phieu"] = row.get("ma_phieu")
        resolved_name, resolved_year = resolve_name_year(
            {
                "ho_ten": data.get("ho_ten") or row.get("ho_ten") or "",
                "nam_sinh": data.get("nam_sinh") or "",
                "file_name": pdf.name,
                "source_file": str(pdf),
            }
        )
        if resolved_name:
            data["ho_ten"] = resolved_name
            row["ho_ten"] = resolved_name
        if resolved_year:
            data["nam_sinh"] = resolved_year
            row["nam_sinh"] = resolved_year

        coverage = data.get("pdf_coverage") or classify_pdf_coverage(data.get("labs") or {})
        data["pdf_coverage"] = coverage
        sample_kind = str(data.get("sample_kind") or "BLOOD_URINE")
        row["last_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ---- Single match path: resolve_tthc_matches (2 TK) ----
        tthc = resolve_tthc_matches(data, index, accounts=accounts)
        if tthc.status == "WAITING_ADMIN" and tthc.mode in {
            "no_name_in_index",
            "params_conflict",
            "no_account_match",
        }:
            # Live search both accounts then re-resolve on a synthetic mini index
            live_name = str(data.get("ho_ten") or row.get("ho_ten") or "")
            live_year = str(data.get("nam_sinh") or resolved_year or "")
            if live_name:
                stats["live_search_attempted"] += 1
                live_st, live_rec, live_acct = search_patient_live_multi(
                    accounts,
                    tokens,
                    name=live_name,
                    year=live_year,
                    date_from=date_from,
                    date_to=date_to,
                    ngay_co_kq=str(data.get("ngay_co_kq") or ""),
                    gioi_tinh=str(data.get("gioi_tinh") or ""),
                    sdt=str(data.get("sdt") or ""),
                )
                if live_st != "WAITING_ADMIN" and live_rec:
                    live_rec["_medinet_account"] = live_acct or live_rec.get(
                        "_medinet_account"
                    )
                    from phase_b_preview import _fold_name as _fn
                    from phase_b_preview import _year_from_ngaysinh as _yf

                    ry = live_year or _yf(live_rec.get("NgaySinh")) or "xxxx"
                    fk = f"{_fn(live_name)}|{ry}"
                    mini = {
                        "by_fold_year": {fk: [live_rec]},
                        "by_name_year": {},
                        "by_phone": {},
                        "by_cccd": {},
                        "by_maphieu": {},
                        "by_pid": {},
                    }
                    tthc2 = resolve_tthc_matches(data, mini, accounts=accounts)
                    if tthc2.status == "READY_IMPORT" and tthc2.matches:
                        tthc = tthc2
                        stats["live_name_match"] += 1
                    elif _fn(str(live_rec.get("HoTen") or "")) == _fn(live_name):
                        from tthc_match import TTHCMatchResult

                        tthc = TTHCMatchResult(
                            "READY_IMPORT", [live_rec], f"live_{live_acct}"
                        )
                        stats["live_name_match"] += 1

        if tthc.status == "AMBIGUOUS_NAME":
            stats["ambiguous_name"] += 1
            _route_pdf_review(
                pdf=pdf,
                row=row,
                under18_dir=under18_dir,
                stats=stats,
                moves=moves,
                note=f"ambiguous_name:{tthc.mode}",
                status="WAITING_ADMIN",
            )
            unmatched_lines.append(
                f"AMBIGUOUS\t{row.get('ho_ten')}\t{tthc.mode}\t{pdf.name}"
            )
            _release_pdf_claim(file_key)
            continue

        if tthc.status != "READY_IMPORT" or not tthc.matches:
            row["status"] = "WAITING_ADMIN"
            row["has_admin_info"] = "NO"
            row["notes"] = f"no_tthc:{tthc.mode}"[:200]
            stats["waiting_admin"] += 1
            stats["no_tthc_both_accounts"] += 1
            unmatched_lines.append(
                f"NO_TTHC_BOTH\t{row.get('ho_ten') or data.get('ho_ten')}\t"
                f"year={data.get('nam_sinh') or resolved_year}\t"
                f"phone={data.get('sdt')}\tmode={tthc.mode}\t{pdf.name}"
            )
            if "/MISSING" not in src_u and "/TK1" not in src_u and "/TK2" not in src_u:
                moved = _move_pdf(pdf, missing)
                if moved:
                    row["source_file"] = str(moved)
                    row["file_name"] = moved.name
                    stats["moved_missing"] += 1
                    moves.append(f"NO_TTHC\t{row.get('ho_ten')}\t{pdf.name}\t->\tMISSING/{moved.name}")
            _release_pdf_claim(file_key)
            continue

        matches = tthc.matches
        n_accts = len(matches)
        label = accounts_label(matches)
        row["has_admin_info"] = "YES"
        row["notes"] = f"tthc_accounts={label};mode={tthc.mode}"[:200]
        stats[f"tthc_mode_{tthc.mode}"] += 1
        for mrec in matches:
            stats[f"matched_{mrec.get('_medinet_account') or 'unknown'}"] += 1

        # OTHER sample (Huyết Trắng etc.) with TTHC → ERROR after optional fill
        force_error = sample_kind == "OTHER"

        if imported_n >= max_per_run:
            row["status"] = "READY_IMPORT"
            row["notes"] = "queued_max_per_run"
            stats["queued"] += 1
            _release_pdf_claim(file_key)
            continue

        if dry_run:
            row["status"] = "READY_IMPORT"
            row["notes"] = f"dry_run;{row['notes']}"[:200]
            stats["dry_run"] += 1
            _release_pdf_claim(file_key)
            continue

        # ---- Dual-write CLS to every matched account ----
        filled_ok = 0
        last_pid = ""
        last_msg = ""
        primary_aid = str(matches[0].get("_medinet_account") or ACCOUNT_TK1)
        any_incomplete = False

        for mrec in matches:
            aid = str(mrec.get("_medinet_account") or primary_aid)
            pid = str(mrec.get("phieukhamId") or mrec.get("Id") or "")
            cdid = mrec.get("cdId")
            if not pid:
                continue
            last_pid = pid
            primary_aid = aid
            row["ma_phieu"] = mrec.get("MaPhieu") or row.get("ma_phieu") or ""

            existing, tokens[aid] = load_cls_view(
                tokens[aid], pid, reauth=make_reauth(mrec)
            )
            payload = labs_to_form_payload(
                data.get("labs") or {},
                phieukham_id=pid,
                gioi_tinh=data.get("gioi_tinh") or "",
            )
            payload["LoaiKham"] = 5152
            if cdid not in (None, ""):
                payload["cdId"] = int(cdid)
            fields_sent = len([k for k in payload if k in LAB_TO_FORM.values()])
            # Điền đủ mọi trường PDF có (kể cả ngoài khoảng tham chiếu).
            # Urea chỉ bỏ qua khi đánh giá "đã đủ" — vẫn gửi nếu PDF có.
            has_cls = cls_has_lab_values(existing)
            missing_on_web = cls_missing_lab_fields(existing, payload) if has_cls else []
            missing_wo_urea = [k for k in missing_on_web if k != "SinhHoaMau_Ure"]
            needs_fill = (not has_cls) or bool(missing_wo_urea) or force or repair

            if not needs_fill and fields_sent > 0:
                filled_ok += 1
                stats["skip_already_cls_acct"] += 1
                continue

            if fields_sent <= 0 and sample_kind == "OTHER":
                # no blood/urine labs to send — still route ERROR
                filled_ok += 1
                last_msg = "other_sample_no_labs"
                continue

            ok, msg, _raw, tokens[aid] = insert_cls(
                tokens[aid], payload, reauth=make_reauth(mrec)
            )
            time.sleep(0.05)
            verified, vdetail, tokens[aid] = verify_cls_saved(
                tokens[aid], pid, payload=payload, reauth=make_reauth(mrec)
            )
            last_msg = f"{msg};{vdetail}"
            existing2, tokens[aid] = load_cls_view(
                tokens[aid], pid, reauth=make_reauth(mrec)
            )
            still = cls_missing_lab_fields(existing2, payload)
            still_wo = [k for k in still if k != "SinhHoaMau_Ure"]
            if ok and verified and fields_sent > 0 and not still_wo:
                filled_ok += 1
                safe_print(
                    f"  DIEN OK [{aid}] {data.get('ho_ten')} pid={pid} "
                    f"fields={fields_sent} coverage={coverage}"
                )
            elif ok and fields_sent > 0:
                filled_ok += 1
                any_incomplete = True
                safe_print(
                    f"  DIEN PARTIAL [{aid}] {data.get('ho_ten')} pid={pid} "
                    f"missing={still_wo[:6]}"
                )
            else:
                stats["error_import"] += 1
                safe_print(f"  ERROR [{aid}] {data.get('ho_ten')} pid={pid} msg={last_msg}")

        attempts = int(row.get("import_attempts") or 0) + 1
        row["import_attempts"] = str(attempts)
        row["imported_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row["notes"] = (
            f"tthc_accounts={label};cls_filled={filled_ok}/{n_accts};"
            f"mode={tthc.mode};{last_msg}"
        )[:200]

        route_coverage = coverage
        if force_error:
            route_coverage = "OTHER"
        if any_incomplete and coverage == "FULL":
            route_coverage = "PARTIAL"

        if filled_ok > 0 or force_error:
            imported_n += 1 if filled_ok else 0
            _route_after_import(
                pdf=pdf,
                row=row,
                pid=last_pid,
                coverage=route_coverage if route_coverage != "OTHER" else "PARTIAL",
                processed=processed,
                error_dir=error_dir,
                under18_dir=under18_dir,
                stats=stats,
                note=row["notes"],
                moves=moves,
                nam_sinh=str(data.get("nam_sinh") or row.get("nam_sinh") or ""),
                tk1_dir=tk1_dir,
                tk2_dir=tk2_dir,
                n_accounts=n_accts,
                primary_account=primary_aid,
                sample_kind=sample_kind,
                force_error=force_error or route_coverage in {"PARTIAL", "URINE_ONLY", "EMPTY", "OTHER"},
            )
            results.append(
                {
                    "file_name": pdf.name,
                    "ho_ten": data.get("ho_ten"),
                    "nam_sinh": data.get("nam_sinh"),
                    "tthc_accounts": label,
                    "phieukhamId": last_pid,
                    "import_status": "IMPORTED" if filled_ok else "ERROR_IMPORT",
                    "message": row["notes"],
                    "verified": "YES" if filled_ok else "NO",
                }
            )
        else:
            row["status"] = "READY_IMPORT"
            row["notes"] = f"import_fail_all:{last_msg}"[:200]
            stats["error_import"] += 1

        if sleep_s:
            time.sleep(sleep_s)
        if imported_n and imported_n % flush_every == 0:
            _flush_cases()
        _release_pdf_claim(file_key)
        continue

    release_owner(owner_tag)

    from single_instance import save_cases_merged

    save_cases_merged(cases_path, rows, write_cases)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # Always write Excel so hourly activity is visible even when 0 imports
    out = build / "excel_preview" / f"CLS_auto_import_{stamp}.xlsx"
    try:
        write_result_excel(results or [], out)
        safe_print(f"Result Excel: {out} (rows={len(results)})")
    except Exception as e:
        safe_print(f"WARN: cannot write result excel: {e}")

    # Heartbeat: proves Task Scheduler actually ran this hour
    try:
        hb_dir = build / "logs"
        hb_dir.mkdir(parents=True, exist_ok=True)
        summary_pre = dict(stats)
        summary_pre["new_files"] = added
        summary_pre["new_files_error"] = added_err
        summary_pre["new_files_missing"] = added_missing
        summary_pre["results"] = len(results)
        summary_pre["mode"] = mode
        hb_line = (
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\t"
            f"mode={mode}\t"
            f"imported={summary_pre.get('imported', 0)}\t"
            f"waiting_admin={summary_pre.get('waiting_admin', 0)}\t"
            f"moved_missing={summary_pre.get('moved_missing', 0)}\t"
            f"new_files={added}\tnew_error={added_err}\t"
            f"results={len(results)}\n"
        )
        (hb_dir / "LAST_HOURLY_OK.txt").write_text(hb_line, encoding="utf-8")
        with (hb_dir / "hourly_heartbeat.log").open("a", encoding="utf-8") as f:
            f.write(hb_line)
    except Exception as e:
        safe_print(f"WARN: heartbeat write failed: {e}")

    # Per-run move log: track which PDFs were actually moved this run.
    try:
        hb_dir = build / "logs"
        hb_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        p = hb_dir / "last_moves.txt"
        header = f"# last_moves | {stamp} | mode={mode} | imported={dict(stats).get('imported', 0)} partial={dict(stats).get('imported_partial_to_error', 0)} moved_missing={dict(stats).get('moved_missing', 0)}"
        body = "\n".join(moves[:5000])
        p.write_text(header + ("\n" + body if body else "\n# 0 moves"), encoding="utf-8")
        safe_print(f"Moves log: {p} (lines={len(moves)})")
    except Exception as e:
        safe_print(f"WARN: moves log write failed: {e}")

    # snapshot ledger
    snap = build / "cases_snapshot" / f"cases-{stamp}.csv"
    try:
        shutil.copy2(cases_path, snap)
    except Exception:
        pass

    counts1 = counts_from_rows(rows)
    d_miss = counts1.get("missing", 0) - counts0.get("missing", 0)
    d_proc = counts1.get("processed", 0) - counts0.get("processed", 0)
    d_err = counts1.get("error", 0) - counts0.get("error", 0)
    d_in = counts1.get("inbox", 0) - counts0.get("inbox", 0)
    safe_print(format_counts_line(counts0, tag="COUNTS_BEFORE"))
    safe_print(format_counts_line(counts1, tag="COUNTS_AFTER"))
    safe_print(
        f"COUNTS_DELTA\tinbox={d_in}\tmissing={d_miss}\terror={d_err}\tprocessed={d_proc}"
    )
    write_last_counts(
        build,
        counts1,
        extra=f"phase=after delta_missing={d_miss} delta_processed={d_proc} delta_error={d_err}",
    )
    missing_pdf_n = counts1.get("missing", missing_pdf_n)
    error_pdf_n = counts1.get("error", error_pdf_n)

    summary = dict(stats)
    summary["mode"] = mode
    summary["new_files"] = added
    summary["new_files_missing"] = added_missing
    summary["results"] = len(results)
    summary["inbox_pdfs"] = inbox_pdf_n
    summary["missing_pdfs"] = missing_pdf_n
    summary["error_pdfs"] = error_pdf_n
    summary["requeued_disk"] = requeued_disk
    summary["skipped_missing_budget"] = stats["skipped_missing_budget"]
    summary["missing_extract_budget"] = missing_budget
    summary["live_name_match"] = stats["live_name_match"]
    summary["live_search_attempted"] = stats["live_search_attempted"]
    summary["unmatched_no_year"] = stats["unmatched_no_year"]
    safe_print(f"Auto cycle stats: {summary}")
    safe_print(
        f"MATCH DIAG: waiting_admin={stats['waiting_admin']} "
        f"live_ok={stats['live_name_match']} live_tried={stats['live_search_attempted']} "
        f"no_year={stats['unmatched_no_year']} imported={stats['imported']} "
        f"partial={stats['imported_partial_to_error']}"
    )
    if stats["waiting_admin"] and stats["live_name_match"] == 0:
        safe_print(
            "HINT: 0 TTHC match. Mo Medinet thu 1 ten trong missing_can_tthc.txt. "
            "Neu web da co TTHC ma bot miss: gui 1 dong NO_TTHC + screenshot form."
        )
        safe_print("HINT: CHI 1 bot. 2 cua so ghi de cases.csv -> DELTA=0 / so sai.")
    # Always refresh MISSING list for TTHC team (even when 0)
    try:
        uout = build / "excel_preview" / "missing_can_tthc.txt"
        uout.parent.mkdir(parents=True, exist_ok=True)
        # keep legacy alias
        legacy = build / "excel_preview" / "hourly_chua_khop_tthc.txt"
        body = (
            f"# missing_can_tthc | {stamp} | mode={mode} | "
            f"ky={date_from}->{date_to}\n"
            "# format: NO_TTHC | ho_ten | year=... | phone=... | pdf\n"
        )
        if unmatched_lines:
            body += "\n".join(unmatched_lines) + "\n"
        else:
            body += "# 0\n"
        uout.write_text(body, encoding="utf-8")
        legacy.write_text(body, encoding="utf-8")
        safe_print(f"MISSING list ({len(unmatched_lines)}): {uout}")
    except Exception as e:
        safe_print(f"WARN unmatched list: {e}")

    try:
        from super_data_status import publish_super_data_status

        g_status = publish_super_data_status(
            local_build=build,
            summary=summary,
            counts_line=format_counts_line(counts1),
            mode=mode,
        )
        if g_status:
            safe_print(f"TIEN DO (G): {g_status}")
        else:
            safe_print(f"TIEN DO (local): {build / 'TIEN_DO_THEO_DOI.txt'}")
    except Exception as e:
        safe_print(f"WARN super_data status: {e}")

    return summary


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--repair",
        action="store_true",
        help="Re-check IMPORTED/ERROR/SKIP; re-import if web empty OR thiếu nước tiểu/sinh hoá",
    )
    ap.add_argument(
        "--full-scan",
        action="store_true",
        help="Quet TOAN BO folder (ke ca PROCESSED). Mac dinh hourly chi INBOX+MISSING",
    )
    ap.add_argument(
        "--audit-processed",
        action="store_true",
        help="Ra soat PROCESSED: khong khop TTHC chinh xac → MISSING",
    )
    ap.add_argument(
        "--missing-budget",
        type=int,
        default=-1,
        help="Cap MISSING rematch (-1=hourly 1500; 0=none; >0=cap). INBOX unlimited.",
    )
    ap.add_argument(
        "--bot",
        choices=["all", "inbox", "missing"],
        default="all",
        help="Bot role for parallel runs: inbox=INBOX only; missing=MISSING only",
    )
    args = ap.parse_args()
    summary = run_auto_cycle(
        dry_run=args.dry_run,
        limit=args.limit,
        force=args.force,
        repair=args.repair,
        full_scan=args.full_scan,
        audit_processed=args.audit_processed,
        missing_budget=args.missing_budget,
        bot_role=args.bot,
    )
    return 2 if summary.get("abort") else 0


if __name__ == "__main__":
    raise SystemExit(main())
