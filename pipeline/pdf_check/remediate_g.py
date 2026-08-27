#!/usr/bin/env python3
"""Dọn G: quét 5 folder, match TTHC 2 TK, điền CLS, move, dedupe.

Thứ tự: PROCESSED → MISSING → UNDER 18 → TK1 → TK2
Bỏ qua: ERROR, INBOX_CLS

Dry-run mặc định; --apply mới ghi G: / Medinet.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()

from auto_cycle import _move_pdf, _route_pdf_review  # noqa: E402
from drive_paths import g_pipeline_live, local_work_build, require_g_on_windows, resolve_g_sync  # noqa: E402
from hourly_sync import read_cases, write_cases  # noqa: E402
from medinet_api import (  # noqa: E402
    LAB_TO_FORM,
    authenticate,
    cls_has_lab_values,
    cls_missing_lab_fields,
    insert_cls,
    labs_to_form_payload,
    load_cls_view,
    verify_cls_saved,
)
from medinet_creds import MEDINET_ACCOUNTS  # noqa: E402
from pdf_extract import classify_pdf_coverage, extract_pdf  # noqa: E402
from phase_b_preview import load_config, load_or_fetch_merged_unit_index, resolve_name_year  # noqa: E402
from scan_pdfs import list_pdfs_in_folder  # noqa: E402
from single_instance import acquire_lock, release_lock, save_cases_merged  # noqa: E402
from tthc_match import (  # noqa: E402
    ACCOUNT_TK1,
    ACCOUNT_TK2,
    account_folder_name,
    resolve_tthc_matches,
)
from write_remediate_excel import write_remediate_excel  # noqa: E402

REMEDIATE_FOLDERS = ("PROCESSED", "MISSING", "UNDER 18", "TK1", "TK2")
DEDUPE_FOLDERS = REMEDIATE_FOLDERS


def _today_dmy() -> str:
    return date.today().strftime("%d/%m/%Y")


def _norm_aid(aid: str) -> str:
    a = (aid or "").strip()
    if a in {ACCOUNT_TK1, "pkdkthuankieu"}:
        return ACCOUNT_TK1
    if a in {ACCOUNT_TK2, "pkdk_Thuankieu"}:
        return ACCOUNT_TK2
    return a


def build_process_queue(sync_root: Path, folders: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    queue: list[dict[str, Any]] = []
    for folder in folders:
        for pdf in list_pdfs_in_folder(sync_root / folder):
            key = pdf.name.lower()
            if key in seen:
                continue
            seen.add(key)
            queue.append({"folder": folder, "path": pdf, "file_name": pdf.name})
    return queue


def find_same_name_paths(sync_root: Path, file_name: str, folders: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for folder in folders:
        p = sync_root / folder / file_name
        if p.is_file():
            out.append(p)
    return out


def dedupe_delete_others(
    sync_root: Path,
    keep: Path,
    file_name: str,
    *,
    apply: bool,
) -> list[str]:
    deleted: list[str] = []
    for p in find_same_name_paths(sync_root, file_name, DEDUPE_FOLDERS):
        try:
            if p.resolve() == keep.resolve():
                continue
        except OSError:
            if str(p) == str(keep):
                continue
        deleted.append(str(p))
        if apply:
            try:
                p.unlink()
            except OSError as e:
                safe_print(f"  WARN xoa trung fail {p}: {e}")
    return deleted


def decide_target_folder(
    *,
    match_status: str,
    tthc_scope: str,
    coverage: str,
    sample_kind: str,
    filled_ok: int,
    n_accts: int,
    cls_tk1: str,
    cls_tk2: str,
    primary_account: str,
) -> str:
    if match_status in {"AMBIGUOUS", "PARSE_FAIL"}:
        return "UNDER 18"
    if match_status != "READY" or tthc_scope in {"", "NONE"}:
        return "MISSING"
    if sample_kind == "OTHER" or coverage not in {"FULL"}:
        return "ERROR"
    if n_accts >= 2 and filled_ok >= 2:
        return "PROCESSED"
    if n_accts >= 2 and filled_ok == 1:
        if cls_tk1 in {"YES", "SKIP"} and cls_tk2 not in {"YES", "SKIP"}:
            return "TK1"
        if cls_tk2 in {"YES", "SKIP"} and cls_tk1 not in {"YES", "SKIP"}:
            return "TK2"
        folder = account_folder_name(primary_account or ACCOUNT_TK1)
        return folder if folder in {"TK1", "TK2"} else "TK1"
    if tthc_scope == "TK2":
        return "TK2"
    if tthc_scope == "TK1":
        return "TK1"
    if tthc_scope == "BOTH":
        return "PROCESSED" if filled_ok >= 2 else "TK1"
    folder = account_folder_name(primary_account or ACCOUNT_TK1)
    return folder if folder in {"TK1", "TK2"} else "TK1"


def dual_write_cls(
    data: dict,
    matches: list[dict],
    *,
    tokens: dict[str, str],
    accounts: list[dict],
    apply: bool,
) -> tuple[int, str, str, str, int, str]:
    by_aid: dict[str, dict] = {}
    for rec in matches:
        aid = _norm_aid(str(rec.get("_medinet_account") or ""))
        if aid:
            by_aid[aid] = rec

    n_accts = len(by_aid) or len(matches)
    filled_ok = 0
    cls_tk1 = "N/A"
    cls_tk2 = "N/A"
    last_msg = ""
    primary_aid = str(matches[0].get("_medinet_account") or ACCOUNT_TK1)
    sample_kind = str(data.get("sample_kind") or "BLOOD_URINE")

    def make_reauth(aid: str):
        def _r():
            for acct in accounts:
                if acct["id"] == aid:
                    tokens[aid] = authenticate(acct["user"], acct["password"])
                    return tokens[aid]
            return tokens.get(aid) or ""

        return _r

    for aid, cls_key in ((ACCOUNT_TK1, "tk1"), (ACCOUNT_TK2, "tk2")):
        if aid not in by_aid:
            if cls_key == "tk1":
                cls_tk1 = "N/A"
            else:
                cls_tk2 = "N/A"
            continue

        mrec = by_aid[aid]
        pid = str(mrec.get("phieukhamId") or mrec.get("Id") or "")
        cdid = mrec.get("cdId")
        primary_aid = aid
        if not pid:
            if cls_key == "tk1":
                cls_tk1 = "NO"
            else:
                cls_tk2 = "NO"
            continue

        if not apply:
            if cls_key == "tk1":
                cls_tk1 = "SKIP"
            else:
                cls_tk2 = "SKIP"
            filled_ok += 1
            continue

        existing, tokens[aid] = load_cls_view(tokens[aid], pid, reauth=make_reauth(aid))
        payload = labs_to_form_payload(
            data.get("labs") or {},
            phieukham_id=pid,
            gioi_tinh=data.get("gioi_tinh") or "",
        )
        payload["LoaiKham"] = 5152
        if cdid not in (None, ""):
            payload["cdId"] = int(cdid)
        fields_sent = len([k for k in payload if k in LAB_TO_FORM.values()])
        has_cls = cls_has_lab_values(existing)
        missing_on_web = cls_missing_lab_fields(existing, payload) if has_cls else []
        missing_wo_urea = [k for k in missing_on_web if k != "SinhHoaMau_Ure"]
        needs_fill = (not has_cls) or bool(missing_wo_urea)

        if not needs_fill and fields_sent > 0:
            filled_ok += 1
            if cls_key == "tk1":
                cls_tk1 = "YES"
            else:
                cls_tk2 = "YES"
            continue

        if fields_sent <= 0 and sample_kind == "OTHER":
            filled_ok += 1
            last_msg = "other_sample_no_labs"
            if cls_key == "tk1":
                cls_tk1 = "YES"
            else:
                cls_tk2 = "YES"
            continue

        ok, msg, _raw, tokens[aid] = insert_cls(tokens[aid], payload, reauth=make_reauth(aid))
        time.sleep(0.05)
        verified, vdetail, tokens[aid] = verify_cls_saved(
            tokens[aid], pid, payload=payload, reauth=make_reauth(aid)
        )
        last_msg = f"{msg};{vdetail}"
        existing2, tokens[aid] = load_cls_view(tokens[aid], pid, reauth=make_reauth(aid))
        still = cls_missing_lab_fields(existing2, payload)
        still_wo = [k for k in still if k != "SinhHoaMau_Ure"]
        if ok and verified and fields_sent > 0 and not still_wo:
            filled_ok += 1
            if cls_key == "tk1":
                cls_tk1 = "YES"
            else:
                cls_tk2 = "YES"
        elif ok and fields_sent > 0:
            filled_ok += 1
            if cls_key == "tk1":
                cls_tk1 = "YES"
            else:
                cls_tk2 = "YES"
        else:
            if cls_key == "tk1":
                cls_tk1 = "NO"
            else:
                cls_tk2 = "NO"

    return filled_ok, cls_tk1, cls_tk2, primary_aid, n_accts, last_msg


def process_one(
    item: dict[str, Any],
    *,
    sync_root: Path,
    index: dict,
    accounts: list[dict],
    tokens: dict[str, str],
    folder_dirs: dict[str, Path],
    apply: bool,
    stats: Counter,
) -> dict[str, Any]:
    pdf: Path = Path(item["path"])
    folder_from = str(item.get("folder") or "")
    row: dict[str, Any] = {
        "file_name": pdf.name,
        "folder_from": folder_from,
        "folder": folder_from,
        "path": str(pdf),
        "ho_ten": "",
        "nam_sinh": "",
        "pdf_coverage": "",
        "sample_kind": "",
        "match_status": "",
        "tthc_scope": "NONE",
        "cls_tk1": "N/A",
        "cls_tk2": "N/A",
        "filled_ok": 0,
        "n_accts": 0,
        "action": "",
        "result": "Dry-run" if not apply else "Thành công",
        "notes": "",
        "folder_to": "",
        "path_final": str(pdf),
        "dedup_deleted": [],
    }

    if not pdf.exists():
        row["result"] = "Lỗi"
        row["notes"] = "PDF không tồn tại"
        row["action"] = "Bỏ qua"
        stats["missing_pdf"] += 1
        return row

    try:
        data = extract_pdf(pdf)
    except Exception as e:
        row["match_status"] = "PARSE_FAIL"
        row["folder_to"] = "UNDER 18"
        row["action"] = "Di chuyển review"
        row["notes"] = f"parse_exc:{e}"[:120]
        stats["parse_error"] += 1
        if apply:
            fake = {"ho_ten": "", "status": "PARSE_ERROR", "notes": row["notes"]}
            _route_pdf_review(
                pdf=pdf,
                row=fake,
                under18_dir=folder_dirs["UNDER 18"],
                stats=stats,
                moves=[],
                note=row["notes"],
            )
            row["path_final"] = fake.get("source_file") or str(pdf)
        return row

    data["file_name"] = pdf.name
    data["source_file"] = str(pdf)
    name, year = resolve_name_year(
        {
            "ho_ten": data.get("ho_ten") or "",
            "nam_sinh": data.get("nam_sinh") or "",
            "file_name": pdf.name,
            "source_file": str(pdf),
        }
    )
    if name:
        data["ho_ten"] = name
    if year:
        data["nam_sinh"] = year

    row["ho_ten"] = str(data.get("ho_ten") or "")
    row["nam_sinh"] = str(data.get("nam_sinh") or "")
    row["pdf_coverage"] = str(
        data.get("pdf_coverage") or classify_pdf_coverage(data.get("labs") or {})
    )
    row["sample_kind"] = str(data.get("sample_kind") or "BLOOD_URINE")

    if not data.get("parse_ok"):
        row["match_status"] = "PARSE_FAIL"
        row["folder_to"] = "UNDER 18"
        row["action"] = "Di chuyển review"
        row["notes"] = "parse_ok=false"
        stats["parse_fail"] += 1
        if apply:
            fake = {"ho_ten": row["ho_ten"], "status": "PARSE_ERROR", "notes": row["notes"]}
            _route_pdf_review(
                pdf=pdf,
                row=fake,
                under18_dir=folder_dirs["UNDER 18"],
                stats=stats,
                moves=[],
                note=row["notes"],
            )
            row["path_final"] = fake.get("source_file") or str(pdf)
        return row

    tthc = resolve_tthc_matches(data, index, accounts=accounts)
    if tthc.status == "AMBIGUOUS_NAME":
        row["match_status"] = "AMBIGUOUS"
        row["tthc_scope"] = "NONE"
        row["folder_to"] = "UNDER 18"
        row["action"] = "Di chuyển review"
        row["notes"] = f"ambiguous:{tthc.mode}"
        stats["ambiguous"] += 1
        if apply:
            fake = {"ho_ten": row["ho_ten"], "status": "WAITING_ADMIN", "notes": row["notes"]}
            _route_pdf_review(
                pdf=pdf,
                row=fake,
                under18_dir=folder_dirs["UNDER 18"],
                stats=stats,
                moves=[],
                note=row["notes"],
            )
            row["path_final"] = fake.get("source_file") or str(pdf)
        return row

    if tthc.status != "READY_IMPORT" or not tthc.matches:
        row["match_status"] = "NO_TTHC"
        row["tthc_scope"] = "NONE"
        row["folder_to"] = "MISSING"
        row["action"] = "Di chuyển MISSING"
        row["notes"] = f"no_tthc:{tthc.mode}"
        stats["no_tthc"] += 1
        dest = folder_dirs["MISSING"]
        if apply:
            moved = _move_pdf(pdf, dest)
            if moved:
                row["path_final"] = str(moved)
            else:
                row["result"] = "Lỗi"
        deleted = dedupe_delete_others(sync_root, Path(row["path_final"]), pdf.name, apply=apply)
        row["dedup_deleted"] = deleted
        if deleted:
            row["action"] = row["action"] + " + xóa trùng"
        return row

    row["match_status"] = "READY"
    by_aid: dict[str, dict] = {}
    for rec in tthc.matches:
        aid = _norm_aid(str(rec.get("_medinet_account") or ""))
        if aid:
            by_aid[aid] = rec
    if ACCOUNT_TK1 in by_aid and ACCOUNT_TK2 in by_aid:
        row["tthc_scope"] = "BOTH"
    elif ACCOUNT_TK2 in by_aid:
        row["tthc_scope"] = "TK2"
    elif ACCOUNT_TK1 in by_aid:
        row["tthc_scope"] = "TK1"
    else:
        row["tthc_scope"] = next(iter(by_aid), "NONE")

    coverage = row["pdf_coverage"]
    sample_kind = row["sample_kind"]
    if sample_kind == "OTHER" or coverage not in {"FULL"}:
        row["folder_to"] = "ERROR"
        row["action"] = "Di chuyển ERROR"
        row["notes"] = f"coverage={coverage};sample={sample_kind}"
        stats["to_error"] += 1
        if apply:
            moved = _move_pdf(pdf, folder_dirs["ERROR"])
            if moved:
                row["path_final"] = str(moved)
        deleted = dedupe_delete_others(sync_root, Path(row["path_final"]), pdf.name, apply=apply)
        row["dedup_deleted"] = deleted
        return row

    filled_ok, cls_tk1, cls_tk2, primary_aid, n_accts, last_msg = dual_write_cls(
        data,
        tthc.matches,
        tokens=tokens,
        accounts=accounts,
        apply=apply,
    )
    row["filled_ok"] = filled_ok
    row["cls_tk1"] = cls_tk1
    row["cls_tk2"] = cls_tk2
    row["n_accts"] = n_accts
    row["notes"] = last_msg

    target = decide_target_folder(
        match_status=row["match_status"],
        tthc_scope=str(row["tthc_scope"]),
        coverage=coverage,
        sample_kind=sample_kind,
        filled_ok=filled_ok,
        n_accts=n_accts,
        cls_tk1=cls_tk1,
        cls_tk2=cls_tk2,
        primary_account=primary_aid,
    )
    row["folder_to"] = target
    row["action"] = "Điền CLS + di chuyển" if apply else "Dry-run: điền CLS + di chuyển"

    dest = folder_dirs.get(target) or folder_dirs["MISSING"]
    keep_path = pdf
    if apply:
        moved = _move_pdf(pdf, dest)
        if moved:
            keep_path = moved
            row["path_final"] = str(moved)
        else:
            row["result"] = "Lỗi"
            row["notes"] = (row["notes"] + ";move_fail")[:200]
            stats["move_fail"] += 1
            return row
        stats[f"routed_{target.lower().replace(' ', '_')}"] += 1

    deleted = dedupe_delete_others(sync_root, keep_path, pdf.name, apply=apply)
    row["dedup_deleted"] = deleted
    if deleted:
        row["action"] = row["action"] + " + xóa trùng"
        stats["dedup_deleted"] += len(deleted)

    return row


def _update_case_row(action_row: dict[str, Any], cases_rows: list[dict]) -> None:
    fname = str(action_row.get("file_name") or "").lower()
    path_final = str(action_row.get("path_final") or "")
    for cr in cases_rows:
        sf = (cr.get("source_file") or "").replace("\\", "/")
        fn = Path(sf).name.lower() if sf else (cr.get("file_name") or "").lower()
        if fn != fname and fname not in sf.lower():
            continue
        cr["source_file"] = path_final
        cr["last_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        folder_to = action_row.get("folder_to") or ""
        if folder_to in {"PROCESSED", "TK1", "TK2"}:
            cr["status"] = "IMPORTED"
            cr["imported_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif folder_to == "MISSING":
            cr["status"] = "WAITING_ADMIN"
        elif folder_to == "ERROR":
            cr["status"] = "ERROR_IMPORT"
        cr["notes"] = f"remediate_g:{action_row.get('notes') or ''}"[:200]
        return
    cases_rows.append(
        {
            "case_key": fname[:16] or "remediate",
            "source_file": path_final,
            "file_hash": "",
            "ho_ten": action_row.get("ho_ten") or "",
            "cccd": "",
            "ngay_kham": "",
            "mau_kham": "",
            "ma_phieu": "",
            "has_lab_file": "YES",
            "has_admin_info": "YES" if action_row.get("tthc_scope") not in {"NONE", ""} else "NO",
            "status": "IMPORTED",
            "import_attempts": "1",
            "last_checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "notes": f"remediate_g_new:{action_row.get('notes') or ''}"[:200],
        }
    )


def run_remediate(*, apply: bool = False, limit: int = 0, folders: tuple[str, ...] | None = None) -> dict:
    lock = acquire_lock("remediate_g")
    if lock is None:
        safe_print("ABORT: remediate_g dang chay (lock).")
        return {"abort": "locked"}

    try:
        if sys.platform.startswith("win") and g_pipeline_live() is None:
            safe_print("ABORT: G: chua mount.")
            return {"abort": "g_missing"}

        cfg = load_config()
        sync = resolve_g_sync(cfg)
        if sys.platform.startswith("win") and not require_g_on_windows(sync):
            safe_print(f"ABORT: chi G: pipeline. sync={sync}")
            return {"abort": "not_g"}

        folder_names = folders or REMEDIATE_FOLDERS
        folder_dirs = {name: sync / name for name in folder_names}
        folder_dirs["ERROR"] = sync / "ERROR"

        build = local_work_build()
        log_dir = build / "logs"
        excel_dir = build / "excel_preview"
        log_dir.mkdir(parents=True, exist_ok=True)

        mode = "APPLY" if apply else "DRY-RUN"
        safe_print(f"========== DON G ({mode}) ==========")
        safe_print(f"SYNC: {sync}")
        safe_print(f"Folders: {', '.join(folder_names)}")

        queue = build_process_queue(sync, folder_names)
        safe_print(f"PDF unique (queue): {len(queue)}")
        if limit > 0:
            queue = queue[:limit]
            safe_print(f"Limited: {len(queue)}")

        accounts = [dict(a) for a in MEDINET_ACCOUNTS[:2]]
        tokens: dict[str, str] = {}
        for acct in accounts:
            tokens[acct["id"]] = authenticate(acct["user"], acct["password"])

        date_from = (cfg.get("medinet") or {}).get("date_from") or "01/07/2026"
        date_to = ((cfg.get("medinet") or {}).get("date_to") or "").strip() or _today_dmy()
        cache_dir = ROOT / "pipeline" / "work" / "index_cache"
        index = load_or_fetch_merged_unit_index(
            accounts, date_from, date_to, cache_dir=cache_dir, max_age_hours=0.0
        )

        cases_path = ROOT / cfg.get("tracking", {}).get("cases_csv", "tracking/cases.csv")
        cases_rows = read_cases(cases_path)

        stats: Counter = Counter()
        results: list[dict] = []
        t0 = time.time()

        for i, item in enumerate(queue, 1):
            pdf_path = Path(item["path"])
            if not pdf_path.exists():
                hits = find_same_name_paths(sync, item["file_name"], folder_names)
                if hits:
                    item["path"] = hits[0]
            result = process_one(
                item,
                sync_root=sync,
                index=index,
                accounts=accounts,
                tokens=tokens,
                folder_dirs=folder_dirs,
                apply=apply,
                stats=stats,
            )
            results.append(result)
            if apply:
                _update_case_row(result, cases_rows)
            if i == 1 or i % 25 == 0 or i == len(queue):
                safe_print(
                    f"  [{i}/{len(queue)}] {result.get('ho_ten') or result.get('file_name')} "
                    f"-> {result.get('folder_to')} filled={result.get('filled_ok')}/{result.get('n_accts')}"
                )

        if apply and results:
            save_cases_merged(cases_path, cases_rows, write_cases)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_xlsx = excel_dir / f"REMEDIATE_{stamp}.xlsx"
        write_remediate_excel(results, out_xlsx)
        out_log = log_dir / f"REMEDIATE_{stamp}.txt"
        lines = [
            f"mode={mode}",
            f"sync={sync}",
            f"total={len(results)}",
            f"elapsed_s={time.time() - t0:.0f}",
            f"excel={out_xlsx}",
            "",
            "stats:",
        ]
        for k, v in stats.most_common():
            lines.append(f"  {k}={v}")
        out_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        safe_print("")
        safe_print(f"Excel: {out_xlsx}")
        safe_print(f"Log: {out_log}")
        safe_print(f"DONE ({mode})")
        return {"ok": True, "mode": mode, "total": len(results), "excel": str(out_xlsx), "stats": dict(stats)}
    finally:
        release_lock(lock)


def main() -> int:
    ap = argparse.ArgumentParser(description="Dọn G: match + CLS + move + dedupe")
    ap.add_argument("--apply", action="store_true", help="Thực thi (mặc định dry-run)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument(
        "--folders",
        default="",
        help="VD: PROCESSED,MISSING (mặc định 5 folder remediation)",
    )
    args = ap.parse_args()
    folders = None
    if (args.folders or "").strip():
        folders = tuple(x.strip() for x in args.folders.split(",") if x.strip())
    res = run_remediate(apply=bool(args.apply), limit=int(args.limit or 0), folders=folders)
    if res.get("abort"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
