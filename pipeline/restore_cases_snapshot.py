#!/usr/bin/env python3
"""Restore tracking/cases.csv from newest local snapshot if ledger is empty.

May A often wipes/empties cases.csv while G: PDFs remain. Snapshots live under
pipeline/work/build/cases_snapshot/ (never on G:).
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tracking" / "cases.csv"
SNAP_DIR = ROOT / "pipeline" / "work" / "build" / "cases_snapshot"


def _row_count(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        from csv_io import open_csv_read

        fctx = open_csv_read(path, newline="")
    except Exception:
        fctx = path.open(encoding="utf-8", errors="replace", newline="")
    with fctx as f:
        try:
            return sum(1 for _ in csv.DictReader(f))
        except Exception:
            return 0


def newest_snapshot() -> Path | None:
    if not SNAP_DIR.exists():
        return None
    cands = sorted(
        SNAP_DIR.glob("cases*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in cands:
        if _row_count(p) > 10:
            return p
    return None


def main() -> int:
    force = "--force" in sys.argv
    n = _row_count(CASES)
    print(f"cases.csv rows={n} path={CASES}")
    if n > 10 and not force:
        print("OK: ledger not empty — skip restore")
        return 0
    snap = newest_snapshot()
    if snap is None:
        print("WARN: no usable snapshot under", SNAP_DIR)
        print("HINT: bots se dang ky lai tu disk (orphan_registered) — chay LAU.")
        return 0
    sn = _row_count(snap)
    print(f"RESTORE from {snap} rows={sn}")
    CASES.parent.mkdir(parents=True, exist_ok=True)
    if CASES.exists():
        bak = CASES.with_suffix(".csv.bak_empty")
        shutil.copy2(CASES, bak)
        print(f"backed empty ledger -> {bak}")
    shutil.copy2(snap, CASES)
    print(f"OK: restored cases.csv rows={_row_count(CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
