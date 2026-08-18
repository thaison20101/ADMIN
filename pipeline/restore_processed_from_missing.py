#!/usr/bin/env python3
"""Move PDFs that were wrongly sent PROCESSED -> MISSING back to PROCESSED.

Full-scan rematch used a thinner Medinet index, so many already-imported PDFs
were treated as 'no TTHC' and moved to MISSING. Those files stay in MISSING
until we put them back; hourly does not restore PROCESSED.

Safe rule: only restore PDFs whose tracking row was IMPORTED / SKIP, or
notes contain keep_processed / imported_full / fullrematch:IMPORTED.

  python .\\pipeline\\restore_processed_from_missing.py --dry-run
  python .\\pipeline\\restore_processed_from_missing.py
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from hourly_sync import read_cases, write_cases  # noqa: E402
from phase_b_preview import load_config  # noqa: E402
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()

KEEP_MARKERS = (
    "IMPORTED",
    "SKIP_ALREADY_CLS",
    "imported_full",
    "keep_processed",
    "already_has_cls",
    "already_on_web",
    "fullrematch:IMPORTED",
    "fullrematch:SKIP",
    "disk_processed",
)


def _drive_dirs(cfg: dict) -> tuple[Path, Path]:
    sync = Path(cfg.get("drive", {}).get("local_sync_root") or "")
    processed = sync / cfg["drive"].get("processed_folder", "PROCESSED")
    missing = sync / cfg["drive"].get("missing_folder", "MISSING")
    return processed, missing


def should_restore(row: dict | None, source_path: str = "") -> bool:
    """True if PDF was previously imported / lived in PROCESSED.

    Tracking is often empty or overwritten to WAITING_ADMIN after full-scan.
    """
    if row is None:
        src = (source_path or "").replace("\\", "/").upper()
        return "/PROCESSED/" in src or src.endswith("/PROCESSED")
    st = (row.get("status") or "").upper()
    notes = str(row.get("notes") or "")
    src = str(row.get("source_file") or source_path or "").replace("\\", "/").upper()
    blob = f"{st} {notes} {src}".upper()
    if any(m.upper() in blob for m in KEEP_MARKERS):
        return True
    if "/PROCESSED/" in src or src.endswith("/PROCESSED"):
        return True
    if "PROCESSED" in blob and "FULLREMATCH" in blob:
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    processed, missing = _drive_dirs(cfg)
    cases_path = ROOT / cfg.get("tracking", {}).get("cases_csv", "tracking/cases.csv")
    rows = read_cases(cases_path)

    by_name: dict[str, dict] = {}
    for r in rows:
        n = (Path(r.get("source_file") or "").name or r.get("file_name") or "").lower()
        if n:
            by_name.setdefault(n, r)

    if not missing.exists():
        safe_print(f"No MISSING folder: {missing}")
        return 0

    moved = 0
    skipped = 0
    processed.mkdir(parents=True, exist_ok=True)
    for pdf in missing.rglob("*.pdf"):
        row = by_name.get(pdf.name.lower())
        if not should_restore(row, source_path=str((row or {}).get("source_file") or pdf)):
            skipped += 1
            continue
        dest = processed / pdf.name
        if dest.exists() and dest.resolve() != pdf.resolve():
            dest = processed / f"{pdf.stem}_restored{pdf.suffix}"
        safe_print(f"RESTORE {pdf.name} -> PROCESSED  notes={(row or {}).get('notes')}")
        if not args.dry_run:
            shutil.move(str(pdf), str(dest))
            if row is None:
                pass
            else:
                row["source_file"] = str(dest)
                row["file_name"] = dest.name
                row["status"] = "IMPORTED"
                row["notes"] = f"restored_from_missing:{row.get('notes') or ''}"[:200]
        moved += 1

    if not args.dry_run:
        write_cases(cases_path, rows)
    safe_print(f"Restored={moved} left_in_missing_unmatched={skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
