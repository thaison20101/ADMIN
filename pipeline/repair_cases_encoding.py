#!/usr/bin/env python3
"""Rewrite tracking/cases.csv as clean UTF-8 (fix mixed encoding crashes).

  python pipeline/repair_cases_encoding.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from csv_io import decode_csv_bytes, open_csv_read  # noqa: E402
from hourly_sync import CASES_CSV, read_cases, write_cases  # noqa: E402
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()


def main() -> int:
    path = CASES_CSV
    if not path.exists():
        safe_print(f"MISSING {path}")
        return 2
    raw = path.read_bytes()
    _text, enc = decode_csv_bytes(raw)
    safe_print(f"Read {path} bytes={len(raw)} detected={enc}")
    rows = read_cases(path)
    bak = path.with_suffix(".csv.bak_encoding")
    bak.write_bytes(raw)
    write_cases(path, rows)
    safe_print(f"Backup -> {bak}")
    safe_print(f"Rewrote UTF-8 rows={len(rows)}")
    # verify
    with open_csv_read(path, newline="") as f:
        n = sum(1 for _ in f) - 1
    safe_print(f"Verify ok lines~={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
