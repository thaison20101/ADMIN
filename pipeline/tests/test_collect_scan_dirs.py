"""Repair/full scan dirs; G offline => MISSING included on full/repair."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from auto_cycle import _collect_scan_dirs  # noqa: E402


def _mk_tree(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    sync = root / "sync"
    for name in (
        "INBOX_CLS",
        "MISSING",
        "ERROR",
        "PROCESSED",
        "UNDER 18",
        "TK1",
        "TK2",
        "CCCD",
    ):
        (sync / name).mkdir(parents=True)
    return sync, sync / "INBOX_CLS", sync / "MISSING", sync / "ERROR", sync / "PROCESSED"


def test_repair_missing_includes_missing_and_cccd():
    with tempfile.TemporaryDirectory() as td:
        sync, inbox, missing, error, processed = _mk_tree(Path(td))
        dirs = _collect_scan_dirs(
            sync, inbox, missing, error, processed,
            full_scan=False, repair=True, bot_role="missing",
        )
        names = {d.name.upper() for d in dirs}
        assert "MISSING" in names
        assert "TK1" in names
        assert "CCCD" in names


def test_full_scan_all_includes_missing_cccd():
    with tempfile.TemporaryDirectory() as td:
        sync, inbox, missing, error, processed = _mk_tree(Path(td))
        dirs = _collect_scan_dirs(
            sync, inbox, missing, error, processed,
            full_scan=True, repair=True, bot_role="all",
        )
        names = {d.name.upper() for d in dirs}
        for must in ("INBOX_CLS", "MISSING", "PROCESSED", "TK1", "TK2", "CCCD"):
            assert must in names, names


def test_hourly_missing_bot_no_disk():
    with tempfile.TemporaryDirectory() as td:
        sync, inbox, missing, error, processed = _mk_tree(Path(td))
        dirs = _collect_scan_dirs(
            sync, inbox, missing, error, processed,
            full_scan=False, repair=False, bot_role="missing",
        )
        assert dirs == []


if __name__ == "__main__":
    test_repair_missing_includes_missing_and_cccd()
    test_full_scan_all_includes_missing_cccd()
    test_hourly_missing_bot_no_disk()
    print("OK")
