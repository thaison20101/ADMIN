#!/usr/bin/env python3
"""One automated cycle: PDF CLS → match Medinet → import.

Routing:
  FULL (mau + sinh hoa, bo qua Ure) → import → PROCESSED
  PARTIAL / URINE_ONLY → import phan co → ERROR
  Khong co TTHC → MISSING (bao bo phan nhap TTHC)

Scan:
  --full-scan (lan dau / bat so): TOAN BO folder duoi pipeline root
    (gom INBOX, MISSING, ERROR, PROCESSED, folder khac) — khong bo sot BN cu
  mac dinh / hourly: chi INBOX_CLS + MISSING

Khop TTHC: ten (ho+ten) + nam sinh + ngay in KQ (~ NgayKham, cho phep in truoc).
Ky quet ngay: 01/07/2026 → hom nay (rolling).
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
    load_or_fetch_unit_index,
    match_patient,
    resolve_name_year,
    search_patient_live,
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
) -> list[Path]:
    """Folders whose PDFs are registered + re-queued this run.

    full_scan=True → TOAN BO (ke ca PROCESSED + UNDER 18) — urea/BN cu.
    repair → INBOX_CLS + ERROR + PROCESSED + UNDER 18.
    hourly → chi INBOX_CLS tren disk; MISSING rematch tu CSV.
    """
    from drive_paths import UNDER18_FOLDER, discover_inbox_dirs

    inbox_dirs = discover_inbox_dirs(sync, inbox)
    under18 = sync / UNDER18_FOLDER
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
    if "/PROCESSED" in u:
        return "processed"
    return "other"


def counts_from_rows(rows: list[dict]) -> dict[str, int]:
    """Folder counts from tracking CSV (no G: listing)."""
    out = {"inbox": 0, "missing": 0, "error": 0, "processed": 0, "under18": 0, "other": 0}
    for r in rows:
        b = _src_bucket(r.get("source_file") or "")
        out[b] = out.get(b, 0) + 1
    return out


def format_counts_line(c: dict[str, int], *, tag: str = "COUNTS") -> str:
    return (
        f"{tag}\tinbox={c.get('inbox', 0)}\tmissing={c.get('missing', 0)}\t"
        f"error={c.get('error', 0)}\tprocessed={c.get('processed', 0)}"
        f"\tunder18={c.get('under18', 0)}"
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
) -> None:
    """FULL adult → PROCESSED; FULL under18 → UNDER 18; PARTIAL → ERROR."""
    is_kid = _patient_under18(nam_sinh or row.get("nam_sinh") or "", pdf.name)
    if coverage == "FULL":
        if is_kid:
            dest = under18_dir
            tag = "UNDER18"
            stats["routed_under18"] += 1
        else:
            dest = processed
            tag = "PROCESSED"
            stats["routed_processed"] += 1
        row["status"] = "IMPORTED"
        row["notes"] = f"imported_full:{note}"[:200]
        stats["imported"] += 1
    else:
        dest = error_dir
        row["status"] = "ERROR_IMPORT"
        row["notes"] = f"imported_{coverage.lower()}_to_error:{note}"[:200]
        stats["imported_partial_to_error"] += 1
        stats["routed_error"] += 1
        tag = "ERROR"
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    moved = _move_pdf(pdf, dest, pid=pid)
    if moved:
        row["source_file"] = str(moved)
        row["file_name"] = moved.name
        if tag in {"PROCESSED", "UNDER18"}:
            try:
                for folder in (error_dir,):
                    for dup in folder.glob(Path(pdf.name).name):
                        if dup.resolve() != Path(moved).resolve():
                            dup.unlink(missing_ok=True)
            except Exception:
                pass
        moves.append(f"{tag}\t{row.get('ho_ten')}\t{pdf.name}\t->\t{dest.name}/{moved.name}")
    elif pdf.exists():
        row["notes"] = f"{row['notes']};move_failed"[:200]
        moves.append(f"{tag}_MOVE_FAIL\t{row.get('ho_ten')}\t{pdf.name}\t->\t{dest.name}")
    safe_print(f"  {tag} coverage={coverage} kid={is_kid} {row.get('ho_ten')} pid={pid}")


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
) -> dict:
    """Process PDFs. Hourly = INBOX+MISSING; full_scan = TOAN BO (ke ca PROCESSED)."""
    from single_instance import acquire_lock, release_lock

    lock = acquire_lock("auto_cycle")
    if lock is None:
        safe_print("ABORT: da co bot khac dang chay (pipeline/work/locks/auto_cycle.lock).")
        safe_print("Chi 1 cua so! Dong bot thu 2 (ghi de cases.csv, DELTA=0 / sai so).")
        return {"abort": "another_instance_running"}
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
    for p in (inbox, processed, error_dir, missing, under18_dir):
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
    # <0 (default): hourly 1500 / repair 0 / full-scan all
    # 0: no MISSING rematch (INBOX-only round)
    # >0: that cap
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

    # full-scan luon kem audit PROCESSED de bat BN cu bi sai / thieu TTHC
    if full_scan:
        audit_processed = True

    mode = "FULL_SCAN" if full_scan else ("REPAIR" if repair else "HOURLY")
    scan_dirs = _collect_scan_dirs(
        sync,
        inbox,
        missing,
        error_dir,
        processed,
        full_scan=full_scan,
        repair=repair,
    )
    safe_print(f"Mode: {mode} | scan dirs ({len(scan_dirs)}): {[d.name for d in scan_dirs]}")
    safe_print(f"MISSING rematch budget this run: {missing_budget}")
    safe_print("Match TTHC: ho + ten (full name tokens dau+cuoi) + nam sinh")
    safe_print("START: INBOX_CLS disk + MISSING CSV | FULL->PROCESSED/UNDER18 PARTIAL->ERROR")
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
    if (not full_scan) and (not repair) and missing_budget > 0:
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

    from medinet_creds import get_medinet_creds

    user, password = get_medinet_creds(cfg)
    token_box = {"t": authenticate(user, password)}

    def reauth():
        token_box["t"] = authenticate(user, password)
        return token_box["t"]

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
    index = load_or_fetch_unit_index(
        token_box["t"],
        date_from,
        date_to,
        cache_dir=cache_dir,
        max_age_hours=index_max_age,
    )
    token_box["t"] = authenticate(user, password)

    stats = Counter()
    results = []
    unmatched_lines = []
    moves: list[str] = []
    imported_n = 0
    incomplete_n = 0

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
            st, rec = match_patient(data, index)
            if st == "WAITING_ADMIN":
                live_st, live_rec, token_box["t"] = search_patient_live(
                    token_box["t"],
                    name=str(data.get("ho_ten") or ""),
                    year=str(data.get("nam_sinh") or ""),
                    date_from=date_from,
                    date_to=date_to,
                    ngay_co_kq=str(data.get("ngay_co_kq") or ""),
                    gioi_tinh=str(data.get("gioi_tinh") or ""),
                    sdt=str(data.get("sdt") or ""),
                )
                if live_st != "WAITING_ADMIN" and live_rec:
                    st, rec = live_st, live_rec
            if st == "WAITING_ADMIN":
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

    # Process INBOX / READY first, then WAITING_ADMIN, then incomplete repair last
    row_order = sorted(range(len(rows)), key=lambda i: (_row_priority(rows[i]), i))
    safe_print(
        f"Priority queue: inbox/ready first; max_import={max_per_run} max_incomplete={max_incomplete}"
    )

    for ri in row_order:
        row = rows[ri]
        status = (row.get("status") or "").upper()

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
        # UNDER 18: hourly skip (da import). Full/repair: kiem urea lai.
        in_under18 = (
            "/UNDER 18/" in src_u or "/UNDER_18/" in src_u or src_u.endswith("/UNDER 18")
        )
        if in_under18 and not full_scan and not repair:
            stats["skipped_under18"] += 1
            continue
        # Hourly: INBOX_CLS + MISSING. Full-scan: moi folder. Repair: INBOX+ERROR+PROCESSED+U18.
        if not full_scan and not repair and not (
            ("/INBOX" in src_u) or ("/MISSING" in src_u)
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
        )

        # Done rows in work folders must still be re-checked against the current
        # web form first. If fields are complete (Ure ignored), later logic will
        # move them to PROCESSED; if fields are missing, later logic will repair.

        if status == "PARSE_ERROR" and not repair and not stuck_in_work:
            stats["skipped_parse"] += 1
            continue

        # Hourly rule: moi PDF trong INBOX/MISSING luon duoc kiem tra lai TTHC.
        # Chi skip IMPORTED/SKIP khi file da nam PROCESSED.
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
                )
            )
            if not needs_recheck:
                stats["skipped_imported" if status == "IMPORTED" else "skipped_already"] += 1
                continue
        if status not in PENDING | {"IMPORTED", "SKIP_ALREADY_CLS", "PARSE_ERROR"}:
            continue

        try:
            data = extract_pdf(pdf)
        except Exception as e:
            row["status"] = "PARSE_ERROR"
            row["notes"] = f"parse:{e}"[:200]
            stats["parse_error"] += 1
            continue

        if not data.get("parse_ok"):
            row["status"] = "PARSE_ERROR"
            row["ho_ten"] = row.get("ho_ten") or data.get("ho_ten") or ""
            row["notes"] = "parse_ok=false"
            stats["parse_error"] += 1
            continue

        row["ho_ten"] = data.get("ho_ten") or row.get("ho_ten") or ""
        row["mau_kham"] = data.get("mau_kham") or row.get("mau_kham") or ""
        data["file_name"] = pdf.name
        data["source_file"] = str(pdf)
        if row.get("ma_phieu"):
            data["ma_phieu"] = row.get("ma_phieu")
        # Sync name/year from filename when PDF body omits nam_sinh
        # (live search previously skipped year="" → mass WAITING_ADMIN).
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
        coverage = data.get("pdf_coverage") or classify_pdf_coverage(data.get("labs") or {})
        data["pdf_coverage"] = coverage
        st, rec = match_patient(data, index)
        row["last_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Live name+year search when day-index missed (common if NgaySinh format
        # or paging skipped the patient). Fixes cases like TRỊNH THẾ NỮ.
        if st == "WAITING_ADMIN":
            live_name = str(data.get("ho_ten") or row.get("ho_ten") or "")
            live_year = str(data.get("nam_sinh") or resolved_year or "")
            if not live_year:
                stats["unmatched_no_year"] += 1
            else:
                stats["live_search_attempted"] += 1
            live_st, live_rec, token_box["t"] = search_patient_live(
                token_box["t"],
                name=live_name,
                year=live_year,
                date_from=date_from,
                date_to=date_to,
                ngay_co_kq=str(data.get("ngay_co_kq") or ""),
                gioi_tinh=str(data.get("gioi_tinh") or ""),
                sdt=str(data.get("sdt") or ""),
            )
            if live_st != "WAITING_ADMIN" and live_rec:
                st, rec = live_st, live_rec
                # Re-check whether CLS already exists
                pid_live = live_rec.get("phieukhamId") or live_rec.get("Id")
                if pid_live not in (None, ""):
                    existing_live, token_box["t"] = load_cls_view(
                        token_box["t"], pid_live, reauth=reauth
                    )
                    if cls_has_lab_values(existing_live):
                        st = "SKIP_ALREADY_CLS"
                stats["live_name_match"] += 1

        if st == "WAITING_ADMIN":
            # PROCESSED already imported: index miss (window/page/cache) must
            # NOT move the PDF to MISSING. Hourly does not re-scan PROCESSED.
            # True wrong-name cases (TRAN SANH vs TRAN NGOC SANH) only move
            # when we *found* a record and name filter rejected it — that
            # still returns WAITING_ADMIN with no rec, same as miss, so we
            # keep PROCESSED to avoid mass false MISSING. Inbox/ERROR still
            # go to MISSING as before.
            if "/PROCESSED" in src_u:
                row["status"] = "IMPORTED"
                row["notes"] = "keep_processed_index_miss"
                stats["keep_processed_index_miss"] += 1
                continue
            row["status"] = "WAITING_ADMIN"
            row["has_admin_info"] = "NO"
            row["notes"] = "no_tthc_match"
            stats["waiting_admin"] += 1
            unmatched_lines.append(
                f"NO_TTHC\t{row.get('ho_ten') or data.get('ho_ten')}\t"
                f"year={data.get('nam_sinh') or resolved_year}\t"
                f"phone={data.get('sdt')}\t{pdf.name}"
            )
            if "/MISSING" not in src_u:
                moved = _move_pdf(pdf, missing)
                if moved:
                    row["source_file"] = str(moved)
                    row["file_name"] = moved.name
                    stats["moved_missing"] += 1
                    moves.append(f"NO_TTHC\t{row.get('ho_ten')}\t{pdf.name}\t->\tMISSING/{moved.name}")
            continue

        # IMPORTANT: UI opens by phieukhamId — never use cdId as save key
        pid = rec.get("phieukhamId") if rec else None
        if pid in (None, ""):
            pid = rec.get("Id") if rec else None
        cdid = rec.get("cdId") if rec else None
        # Guard: cdId must not be mistaken for phieukhamId
        if rec and cdid not in (None, "") and pid not in (None, "") and int(pid) == int(cdid):
            # extremely rare; keep phieukhamId field explicitly
            pid = rec.get("phieukhamId") or pid
        pid = str(pid or "")
        if rec:
            row["ma_phieu"] = rec.get("MaPhieu") or row.get("ma_phieu") or ""
            row["has_admin_info"] = "YES"

        if st == "SKIP_ALREADY_CLS":
            # List says already has CLS — during repair/force fall through so we
            # can still fill missing urine (Âm tính→Negative) / Urê / etc.
            # Also when PDF still stuck in work folders: re-check gaps then move.
            existing_early, token_box["t"] = (
                load_cls_view(token_box["t"], pid, reauth=reauth) if pid else (None, token_box["t"])
            )
            if not cls_has_lab_values(existing_early):
                st = "READY_IMPORT"
            elif force or repair or stuck_in_work:
                st = "READY_IMPORT"  # re-evaluate incompleteness below
            else:
                # Already on web and not stuck — still route by PDF coverage
                payload_early = labs_to_form_payload(
                    data.get("labs") or {},
                    phieukham_id=pid,
                    gioi_tinh=data.get("gioi_tinh") or "",
                )
                miss_e = [
                    k
                    for k in cls_missing_lab_fields(existing_early, payload_early)
                ]
                missing_wo_urea = [k for k in miss_e if k != "SinhHoaMau_Ure"]
                payload_has_urea = payload_early.get("SinhHoaMau_Ure") not in (None, "")
                urea_missing_only = ("SinhHoaMau_Ure" in miss_e) and (not missing_wo_urea)
                if missing_wo_urea or (urea_missing_only and payload_has_urea):
                    st = "READY_IMPORT"
                else:
                    _route_after_import(
                        pdf=pdf,
                        row=row,
                        pid=pid,
                        coverage=coverage,
                        processed=processed,
                        error_dir=error_dir,
                        under18_dir=under18_dir,
                        stats=stats,
                        note="already_has_cls",
                        moves=moves,
                        nam_sinh=str(row.get("nam_sinh") or data.get("nam_sinh") or ""),
                    )
                    continue

        if not pid:
            row["status"] = "WAITING_ADMIN"
            row["notes"] = "missing_phieukhamId"
            stats["waiting_admin"] += 1
            continue

        existing, token_box["t"] = load_cls_view(token_box["t"], pid, reauth=reauth)
        has_cls = cls_has_lab_values(existing)

        # Build payload early so repair can detect incomplete urine/chemistry
        payload = labs_to_form_payload(
            data.get("labs") or {},
            phieukham_id=pid,
            gioi_tinh=data.get("gioi_tinh") or "",
        )
        payload["LoaiKham"] = 5152
        if cdid not in (None, ""):
            payload["cdId"] = int(cdid)
        fields_sent = len([k for k in payload if k in LAB_TO_FORM.values()])
        missing_on_web = cls_missing_lab_fields(existing, payload) if has_cls else []
        # Hourly: defer Urobilinogen-only gaps to CHAY_REPAIR_URO.ps1
        # (otherwise hundreds of REPAIR incomplete burn all import slots)
        if not repair and missing_on_web == ["NuocTieu_Urobilinogen"]:
            stats["defer_urobilinogen"] += 1
            missing_on_web = []
        notes_prev = str(row.get("notes") or "")
        looks_incomplete = has_cls and web_cls_looks_incomplete(existing, payload)
        if not repair and looks_incomplete:
            # same defer if the only payload gap is urobilinogen
            miss2 = cls_missing_lab_fields(existing, payload)
            miss2 = [k for k in miss2 if k not in {"NuocTieu_Urobilinogen"}]
            if not miss2 and "NuocTieu_Urobilinogen" in (cls_missing_lab_fields(existing, payload) or []):
                looks_incomplete = False
                stats["defer_urobilinogen"] += 1
        needs_urine_fix = (
            "SET-no-urine-text" in notes_prev
            or "SET-urine-all-dropped" in notes_prev
            or "incomplete_after_save" in notes_prev
            or looks_incomplete
            or (has_cls and bool(missing_on_web))
            or (has_cls and cls_urine_incomplete(existing, payload) and repair)
        )
        force_this = force or needs_urine_fix

        if has_cls and not force_this:
            # Web already has all PDF fields (Ure ignored) — route by PDF coverage
            missing_all = cls_missing_lab_fields(existing, payload)
            missing_wo_urea = [k for k in missing_all if k != "SinhHoaMau_Ure"]
            payload_has_urea = payload.get("SinhHoaMau_Ure") not in (None, "")
            urea_missing_only = ("SinhHoaMau_Ure" in missing_all) and (not missing_wo_urea)
            if missing_wo_urea or (urea_missing_only and payload_has_urea):
                # If web thiếu đúng Urea mà PDF có Urea → vẫn ép import để fill Urea.
                row["status"] = "READY_IMPORT"
                if missing_wo_urea:
                    row["notes"] = f"incomplete_keep_work:{','.join(missing_wo_urea[:8])}"[:200]
                else:
                    row["notes"] = "force_urea_missing_only"
                stats["force_urea_repair"] += 1
                stats["incomplete_block_move"] += 1
                if "/PROCESSED" in src_u:
                    moved_back = _move_pdf(pdf, inbox, pid=pid)
                    if moved_back:
                        row["source_file"] = str(moved_back)
                        row["file_name"] = moved_back.name
                continue
            row["imported_at"] = row.get("imported_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _route_after_import(
                pdf=pdf,
                row=row,
                pid=pid,
                coverage=coverage,
                processed=processed,
                error_dir=error_dir,
                under18_dir=under18_dir,
                stats=stats,
                note="already_on_web",
                moves=moves,
                nam_sinh=str(data.get("nam_sinh") or row.get("nam_sinh") or ""),
            )
            continue
        if not has_cls or needs_urine_fix:
            why = "empty-on-web" if not has_cls else f"incomplete:{','.join(missing_on_web[:8]) or 'heuristic'}"
            if repair or needs_urine_fix:
                safe_print(f"  REPAIR {why} {row.get('ho_ten')} pid={pid} coverage={coverage}")
                stats["repair_empty" if not has_cls else "repair_incomplete"] += 1
            row["status"] = "READY_IMPORT"
            if needs_urine_fix:
                row["import_attempts"] = "0"

        # Cap incomplete overwrites so NEW inbox imports still get slots
        if has_cls and needs_urine_fix:
            if incomplete_n >= max_incomplete:
                row["status"] = "READY_IMPORT"
                row["notes"] = "queued_incomplete_cap"
                stats["queued_incomplete"] += 1
                continue
            incomplete_n += 1

        if imported_n >= max_per_run:
            row["status"] = "READY_IMPORT"
            row["notes"] = "queued_max_per_run"
            stats["queued"] += 1
            continue

        result_row = {
            "file_name": pdf.name,
            "ho_ten": data.get("ho_ten"),
            "nam_sinh": data.get("nam_sinh"),
            "mau_kham": data.get("mau_kham"),
            "medinet_MaPhieu": row.get("ma_phieu"),
            "phieukhamId": pid,
            "cdId": cdid or "",
            "fields_sent": fields_sent,
        }

        if dry_run:
            row["status"] = "READY_IMPORT"
            row["notes"] = "dry_run"
            result_row.update({"import_status": "DRY_RUN", "message": "dry_run", "verified": "NO"})
            results.append(result_row)
            stats["dry_run"] += 1
            continue

        ok, msg, _raw, token_box["t"] = insert_cls(token_box["t"], payload, reauth=reauth)
        time.sleep(0.05)
        verified, vdetail, token_box["t"] = verify_cls_saved(
            token_box["t"], pid, payload=payload, reauth=reauth
        )
        attempts = int(row.get("import_attempts") or 0) + 1
        row["import_attempts"] = str(attempts)
        msg = f"{msg}; {vdetail}"

        # Re-check web after save via Get+FormViewer (Get alone often omits Urobilinogen)
        existing2, token_box["t"] = load_cls_view(token_box["t"], pid, reauth=reauth)
        # Ignore urine fields Medinet rejected during progressive retry
        dropped = []
        dm = re.search(r"dropped=([^:;]+)", msg or "")
        if dm:
            dropped = [x.strip() for x in dm.group(1).split(",") if x.strip()]
        check_payload = {k: v for k, v in payload.items() if k not in dropped}
        still_missing = cls_missing_lab_fields(existing2, check_payload)
        urine_ok = not cls_urine_incomplete(existing2, check_payload)
        partial_bad = ("SET-no-urine-text" in (msg or "")) or ("SET-urine-all-dropped" in (msg or ""))

        if ok and verified and fields_sent > 0 and urine_ok and not partial_bad:
            # keep urea in still_missing when PDF has it
            if still_missing:
                # PDF fields still empty on web — keep retrying (do not park yet)
                row["status"] = "READY_IMPORT"
                row["notes"] = f"incomplete_after_save:{','.join(still_missing[:10])};{msg}"[:200]
                result_row.update(
                    {
                        "import_status": "ERROR_IMPORT",
                        "message": row["notes"],
                        "verified": "PARTIAL",
                    }
                )
                stats["error_import"] += 1
                safe_print(
                    f"  INCOMPLETE {data.get('ho_ten')} pid={pid} missing={still_missing[:8]} coverage={coverage}"
                )
                results.append(result_row)
                if sleep_s:
                    time.sleep(sleep_s)
                continue
            # All PDF fields (except Ure) are on web → route by coverage
            row["imported_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result_row.update(
                {
                    "import_status": "IMPORTED" if coverage == "FULL" else f"IMPORTED_{coverage}",
                    "message": f"{msg};coverage={coverage}",
                    "verified": "YES",
                }
            )
            imported_n += 1
            _route_after_import(
                pdf=pdf,
                row=row,
                pid=pid,
                coverage=coverage,
                processed=processed,
                error_dir=error_dir,
                under18_dir=under18_dir,
                stats=stats,
                note=msg or "imported",
                moves=moves,
                nam_sinh=str(data.get("nam_sinh") or row.get("nam_sinh") or ""),
            )
            safe_print(f"  SAVED {data.get('ho_ten')} pid={pid} fields={fields_sent} coverage={coverage}")
        else:
            max_attempts = int(cfg.get("tracking", {}).get("max_import_attempts", 5))
            # repair: keep retrying instead of parking forever in ERROR
            if repair:
                row["status"] = "READY_IMPORT"
                row["import_attempts"] = "0"
            else:
                row["status"] = "ERROR_IMPORT" if attempts >= max_attempts else "READY_IMPORT"
            row["notes"] = f"import_fail:{msg}"[:200]
            result_row.update(
                {
                    "import_status": "ERROR_IMPORT",
                    "message": msg,
                    "verified": "YES" if verified else "NO",
                }
            )
            stats["error_import"] += 1
            # Hard fail only (non-repair): park PDF in ERROR for visibility
            if (not repair) and row["status"] == "ERROR_IMPORT" and pdf.exists():
                moved = _move_pdf(pdf, error_dir, pid=pid)
                if moved:
                    row["source_file"] = str(moved)
                    moves.append(f"IMPORT_FAIL\t{data.get('ho_ten')}\t{pdf.name}\t->\tERROR/{moved.name}")
            safe_print(f"  ERROR {data.get('ho_ten')} pid={pid} msg={msg}")

        results.append(result_row)
        if sleep_s:
            time.sleep(sleep_s)

    write_cases(cases_path, rows)

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
        help="Ra soat PROCESSED: khong khop TTHC (ten+nam sinh+ngay in KQ) → MISSING",
    )
    ap.add_argument(
        "--missing-budget",
        type=int,
        default=-1,
        help="Cap MISSING rematch (-1=hourly 1500; 0=none; >0=cap). INBOX unlimited.",
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
    )
    return 2 if summary.get("abort") else 0


if __name__ == "__main__":
    raise SystemExit(main())
