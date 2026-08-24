#!/usr/bin/env python3
"""CLI: scan all pipeline PDFs, match TTHC (2 TK), check CLS — NO import.

  python pipeline/pdf_check/run_check.py
  python pipeline/pdf_check/run_check.py --skip-cls --limit 200
  python pipeline/pdf_check/run_check.py --folders PROCESSED,MISSING --hash
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()

from check_tthc_cls import check_one_pdf  # noqa: E402
from dedup import mark_duplicates  # noqa: E402
from drive_paths import g_pipeline_live, local_work_build, resolve_g_sync  # noqa: E402
from medinet_api import authenticate  # noqa: E402
from medinet_creds import MEDINET_ACCOUNTS  # noqa: E402
from phase_b_preview import load_config, load_or_fetch_merged_unit_index  # noqa: E402
from scan_pdfs import DEFAULT_FOLDERS, scan_pipeline_pdfs  # noqa: E402
from write_excel import write_pdf_check_excel  # noqa: E402


def _today_dmy() -> str:
    return date.today().strftime("%d/%m/%Y")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="PDF CHECK: TTHC 2 TK + CLS + dedup (KHONG import)"
    )
    ap.add_argument("--limit", type=int, default=0, help="Max PDFs (0=all)")
    ap.add_argument(
        "--folders",
        default="",
        help="Comma list e.g. PROCESSED,MISSING (default=all pipeline folders)",
    )
    ap.add_argument(
        "--skip-cls",
        action="store_true",
        help="Do not call load_cls_view (faster; TTHC + dedup only)",
    )
    ap.add_argument(
        "--hash",
        action="store_true",
        help="Compute content hash to confirm true duplicates",
    )
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.05,
        help="Sleep seconds between CLS API calls",
    )
    ap.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print progress every N PDFs",
    )
    args = ap.parse_args()

    safe_print("========== PDF CHECK (KHONG IMPORT) ==========")
    if sys.platform.startswith("win") and g_pipeline_live() is None:
        safe_print("ABORT: G: chua mount — mo Google Drive Desktop")
        return 2

    cfg = load_config()
    sync = resolve_g_sync(cfg)
    build = local_work_build()
    excel_dir = build / "excel_preview"
    excel_dir.mkdir(parents=True, exist_ok=True)

    folder_list: list[str] | None = None
    if (args.folders or "").strip():
        folder_list = [x.strip() for x in args.folders.split(",") if x.strip()]
    else:
        folder_list = list(DEFAULT_FOLDERS)

    safe_print(f"SYNC: {sync}")
    safe_print(f"Folders: {', '.join(folder_list)}")
    safe_print(f"skip_cls={args.skip_cls} hash={args.hash} limit={args.limit}")

    scanned = scan_pipeline_pdfs(sync, folder_list)
    safe_print(f"PDF scanned: {len(scanned)}")
    if args.limit and args.limit > 0:
        scanned = scanned[: args.limit]
        safe_print(f"Limited to: {len(scanned)}")

    scanned = mark_duplicates(scanned, compute_hash=bool(args.hash))
    n_dup = sum(1 for r in scanned if r.get("is_dup_name") == "YES")
    safe_print(f"Dup name rows: {n_dup}")

    # Always use the 2 hardcoded PKDK Medinet accounts (same as hourly/import).
    # Do not take alternate accounts from config.local.json for this check tool.
    accounts = [dict(a) for a in MEDINET_ACCOUNTS[:2]]
    safe_print(
        f"Accounts (hardcoded): {accounts[0]['user']} + {accounts[1]['user']}"
    )
    tokens: dict[str, str] = {}
    for acct in accounts:
        tokens[acct["id"]] = authenticate(acct["user"], acct["password"])
        safe_print(f"  Auth OK [{acct['id']}] user={acct['user']}")

    date_from = (cfg.get("medinet") or {}).get("date_from") or "01/07/2026"
    date_to = ((cfg.get("medinet") or {}).get("date_to") or "").strip() or _today_dmy()
    cache_dir = ROOT / "pipeline" / "work" / "index_cache"
    safe_print(f"Index Medinet {date_from} -> {date_to} ...")
    index = load_or_fetch_merged_unit_index(
        accounts,
        date_from,
        date_to,
        cache_dir=cache_dir,
        max_age_hours=3.0,
    )
    safe_print(f"Index ids={len(index.get('all_ids') or set())}")

    results: list[dict] = []
    t0 = time.time()
    for i, item in enumerate(scanned, 1):
        pdf = Path(item["path"])
        folder = str(item.get("folder") or "")
        try:
            checked = check_one_pdf(
                pdf,
                folder=folder,
                index=index,
                accounts=accounts,
                tokens=tokens,
                skip_cls=bool(args.skip_cls),
                sleep_s=float(args.sleep),
            )
        except Exception as e:
            checked = {
                "folder": folder,
                "file_name": pdf.name,
                "path": str(pdf),
                "match_status": "ERROR",
                "match_mode": f"check_exc:{e}"[:80],
                "cls_summary": "ERROR",
                "tthc_scope": "NONE",
            }
        # merge dup fields from scan
        for k in (
            "is_dup_name",
            "dup_folders",
            "dup_count",
            "same_hash_dup",
            "hash_dup_folders",
            "file_hash",
        ):
            checked[k] = item.get(k, "")
        results.append(checked)
        if i == 1 or i % max(1, args.progress_every) == 0 or i == len(scanned):
            elapsed = time.time() - t0
            safe_print(
                f"  [{i}/{len(scanned)}] {elapsed:.0f}s "
                f"{checked.get('ho_ten') or pdf.name} "
                f"scope={checked.get('tthc_scope')} cls={checked.get('cls_summary')}"
            )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_xlsx = excel_dir / f"PDF_CHECK_{stamp}.xlsx"
    write_pdf_check_excel(results, out_xlsx)
    out_txt = excel_dir / f"PDF_CHECK_{stamp}_summary.txt"
    from collections import Counter

    lines = [
        f"stamp={stamp}",
        f"sync={sync}",
        f"total={len(results)}",
        f"skip_cls={args.skip_cls}",
        f"excel={out_xlsx}",
        "",
        "cls_summary:",
    ]
    for k, v in Counter(str(r.get("cls_summary") or "") for r in results).most_common():
        lines.append(f"  {k}={v}")
    lines.append("tthc_scope:")
    for k, v in Counter(str(r.get("tthc_scope") or "") for r in results).most_common():
        lines.append(f"  {k}={v}")
    lines.append(f"dup_name={sum(1 for r in results if r.get('is_dup_name')=='YES')}")
    lines.append(
        "folder_mismatch="
        + str(
            sum(
                1
                for r in results
                if r.get("folder_nen")
                and r.get("folder")
                and str(r.get("folder")) != str(r.get("folder_nen"))
                and str(r.get("match_status") or "") == "READY"
            )
        )
    )
    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    safe_print("")
    safe_print(f"Excel: {out_xlsx}")
    safe_print(f"Summary: {out_txt}")
    safe_print("Sheets: Tất cả | Trùng tên | Cần điền CLS | Đã có CLS | Không TTHC | Mơ hồ | Sai folder | Tóm tắt")
    safe_print("DONE (no import, no move)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
