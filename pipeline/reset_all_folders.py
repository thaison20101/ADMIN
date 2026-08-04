#!/usr/bin/env python3
"""Reset ALL work PDFs in INBOX + ERROR + (optional) incomplete PROCESSED.

  python .\\pipeline\\reset_all_folders.py
  python .\\pipeline\\reset_all_folders.py --include-processed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hourly_sync import read_cases, register_new_files, sha256_file, write_cases  # noqa: E402
from phase_b_preview import load_config  # noqa: E402
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--include-processed",
        action="store_true",
        help="Also requeue PROCESSED PDFs for full re-check/repair",
    )
    args = ap.parse_args()

    cfg = load_config()
    sync = Path(cfg.get("drive", {}).get("local_sync_root") or "")
    inbox = sync / cfg["drive"]["inbox_folder"] if sync.exists() else ROOT / "INBOX_CLS"
    error = sync / cfg["drive"]["error_folder"] if sync.exists() else ROOT / "ERROR"
    processed = sync / cfg["drive"]["processed_folder"] if sync.exists() else ROOT / "PROCESSED"
    cases_path = ROOT / cfg.get("tracking", {}).get("cases_csv", "tracking/cases.csv")

    rows = read_cases(cases_path)
    folders = [("inbox", inbox), ("error", error)]
    if args.include_processed:
        folders.append(("processed", processed))

    added = 0
    for tag, folder in folders:
        if folder.exists():
            added += register_new_files(folder, rows)

    by_name = {}
    by_hash = {r.get("file_hash"): r for r in rows if r.get("file_hash")}
    for r in rows:
        nm = (Path(r.get("source_file") or "").name or r.get("file_name") or "").lower()
        if nm:
            by_name[nm] = r

    reset_n = 0
    for tag, folder in folders:
        if not folder.exists():
            continue
        for pdf in folder.rglob("*.pdf"):
            key = pdf.name.lower()
            r = by_name.get(key)
            if r is None:
                try:
                    digest = sha256_file(pdf)
                except Exception:
                    digest = ""
                r = by_hash.get(digest) if digest else None
            if r is None:
                continue
            old = (r.get("status") or "").upper()
            r["source_file"] = str(pdf)
            r["file_name"] = pdf.name
            r["status"] = "READY_IMPORT"
            r["import_attempts"] = "0"
            r["notes"] = f"full_folder_reset:{tag}:{old}"[:200]
            reset_n += 1
            by_name[key] = r

    write_cases(cases_path, rows)
    safe_print("========== RESET ALL FOLDERS ==========")
    for tag, folder in folders:
        n = len(list(folder.rglob("*.pdf"))) if folder.exists() else 0
        safe_print(f"{tag}: {folder} pdfs={n}")
    safe_print(f"Registered new: {added}")
    safe_print(f"Re-queued rows: {reset_n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
