#!/usr/bin/env python3
"""Force re-queue every PDF still in INBOX_CLS / ERROR for full re-check.

TTHC may already be on Medinet while tracking still says WAITING_ADMIN /
SKIP / IMPORTED — this resets those rows so --repair can match + import +
move to PROCESSED.

  python .\\pipeline\\reset_inbox_queue.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hourly_sync import read_cases, register_new_files, write_cases  # noqa: E402
from phase_b_preview import load_config  # noqa: E402
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()


def main() -> int:
    cfg = load_config()
    sync = Path(cfg.get("drive", {}).get("local_sync_root") or "")
    inbox = sync / cfg["drive"]["inbox_folder"] if sync.exists() else ROOT / "INBOX_CLS"
    error = sync / cfg["drive"]["error_folder"] if sync.exists() else ROOT / "ERROR"
    cases_path = ROOT / cfg.get("tracking", {}).get("cases_csv", "tracking/cases.csv")

    rows = read_cases(cases_path)
    added_i = register_new_files(inbox, rows) if inbox.exists() else 0
    added_e = register_new_files(error, rows) if error.exists() else 0

    # Index PDF names still in work folders
    work_names: set[str] = set()
    work_paths: dict[str, Path] = {}
    for base in (inbox, error):
        if not base.exists():
            continue
        for p in base.rglob("*.pdf"):
            work_names.add(p.name.lower())
            work_paths[p.name.lower()] = p

    reset_n = 0
    for r in rows:
        src = Path(r.get("source_file") or "")
        name = (src.name or r.get("file_name") or "").lower()
        src_u = str(src).replace("\\", "/").upper()
        in_work = (
            ("/INBOX" in src_u)
            or ("/ERROR" in src_u)
            or (name and name in work_names)
        )
        if not in_work:
            continue
        # Point source_file at the live INBOX/ERROR path when possible
        if name in work_paths:
            r["source_file"] = str(work_paths[name])
            r["file_name"] = work_paths[name].name
        old = (r.get("status") or "").upper()
        r["status"] = "READY_IMPORT"
        r["import_attempts"] = "0"
        r["notes"] = f"full_recheck_reset:{old}"[:200]
        reset_n += 1

    write_cases(cases_path, rows)
    safe_print("========== RESET INBOX/ERROR QUEUE ==========")
    safe_print(f"Inbox folder : {inbox}")
    safe_print(f"Error folder : {error}")
    safe_print(f"PDFs on disk : {len(work_names)}")
    safe_print(f"New registered: inbox={added_i} error={added_e}")
    safe_print(f"Re-queued rows: {reset_n} -> READY_IMPORT")
    safe_print(f"Ledger: {cases_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
