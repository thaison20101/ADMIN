#!/usr/bin/env python3
"""Print COUNTS from tracking CSV (no 10k G: listing).

Same line format as print_drive_dirs:
  COUNTS\\tinbox=N\\tmissing=N\\terror=N\\tprocessed=N\\tunder18=N

Usage: python pipeline/print_counts.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tracking" / "cases.csv"


def _bucket(src: str) -> str:
    u = (src or "").replace("\\", "/").upper()
    if "/UNDER 18/" in u or "/UNDER_18/" in u or u.endswith("/UNDER 18"):
        return "under18"
    if "/INBOX" in u or "INBOX_CLS" in u:
        return "inbox"
    if "/MISSING/" in f"/{u}/" or u.endswith("/MISSING"):
        return "missing"
    if "/ERROR/" in f"/{u}/" or u.endswith("/ERROR"):
        return "error"
    if "/PROCESSED" in u:
        return "processed"
    return "other"


def counts_from_csv(path: Path) -> dict[str, int]:
    out = {"inbox": 0, "missing": 0, "error": 0, "processed": 0, "under18": 0, "other": 0}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            b = _bucket(r.get("source_file") or "")
            out[b] = out.get(b, 0) + 1
    return out


def main() -> int:
    c = counts_from_csv(CASES)
    print(CASES)
    print(
        f"COUNTS\tinbox={c['inbox']}\tmissing={c['missing']}\t"
        f"error={c['error']}\tprocessed={c['processed']}\tunder18={c['under18']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
