"""Repair/full scan dirs must include TK1/TK2; repair must not walk MISSING."""
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
    ):
        (sync / name).mkdir(parents=True)
    inbox = sync / "INBOX_CLS"
    missing = sync / "MISSING"
    error = sync / "ERROR"
    processed = sync / "PROCESSED"
    return sync, inbox, missing, error, processed


def test_repair_all_includes_tk1_tk2_not_missing():
    with tempfile.TemporaryDirectory() as td:
        sync, inbox, missing, error, processed = _mk_tree(Path(td))
        dirs = _collect_scan_dirs(
            sync,
            inbox,
            missing,
            error,
            processed,
            full_scan=False,
            repair=True,
            bot_role="all",
        )
        names = {d.name.upper() for d in dirs}
        assert "TK1" in names
        assert "TK2" in names
        assert "PROCESSED" in names
        assert "ERROR" in names
        assert "MISSING" not in names


def test_repair_missing_bot_fillable_only():
    with tempfile.TemporaryDirectory() as td:
        sync, inbox, missing, error, processed = _mk_tree(Path(td))
        dirs = _collect_scan_dirs(
            sync,
            inbox,
            missing,
            error,
            processed,
            full_scan=False,
            repair=True,
            bot_role="missing",
        )
        names = {d.name.upper() for d in dirs}
        assert "TK1" in names
        assert "TK2" in names
        assert "PROCESSED" in names
        assert "MISSING" not in names


def test_full_scan_missing_includes_tk_and_missing():
    with tempfile.TemporaryDirectory() as td:
        sync, inbox, missing, error, processed = _mk_tree(Path(td))
        dirs = _collect_scan_dirs(
            sync,
            inbox,
            missing,
            error,
            processed,
            full_scan=True,
            repair=True,
            bot_role="missing",
        )
        names = {d.name.upper() for d in dirs}
        assert "MISSING" in names
        assert "TK1" in names
        assert "TK2" in names


def test_full_scan_all_includes_processed_tk():
    with tempfile.TemporaryDirectory() as td:
        sync, inbox, missing, error, processed = _mk_tree(Path(td))
        dirs = _collect_scan_dirs(
            sync,
            inbox,
            missing,
            error,
            processed,
            full_scan=True,
            repair=True,
            bot_role="all",
        )
        names = {d.name.upper() for d in dirs}
        for must in ("INBOX_CLS", "ERROR", "PROCESSED", "UNDER 18", "TK1", "TK2", "MISSING"):
            assert must in names, f"full-scan all missing {must}: {names}"


def test_repair_requeues_imported_via_status_gate():
    """repair=True scan dirs must include TK1 for IMPORTED recheck path."""
    with tempfile.TemporaryDirectory() as td:
        sync, inbox, missing, error, processed = _mk_tree(Path(td))
        dirs = _collect_scan_dirs(
            sync,
            inbox,
            missing,
            error,
            processed,
            full_scan=False,
            repair=True,
            bot_role="all",
        )
        assert any(d.name.upper() == "TK1" for d in dirs)


def test_repair_inbox_bot_only_inbox_error():
    with tempfile.TemporaryDirectory() as td:
        sync, inbox, missing, error, processed = _mk_tree(Path(td))
        dirs = _collect_scan_dirs(
            sync,
            inbox,
            missing,
            error,
            processed,
            full_scan=False,
            repair=True,
            bot_role="inbox",
        )
        names = {d.name.upper() for d in dirs}
        assert "INBOX_CLS" in names
        assert "ERROR" in names
        assert "PROCESSED" not in names
        assert "TK1" not in names


if __name__ == "__main__":
    test_repair_all_includes_tk1_tk2_not_missing()
    test_repair_missing_bot_fillable_only()
    test_full_scan_missing_includes_tk_and_missing()
    test_repair_requeues_imported_via_status_gate()
    test_full_scan_all_includes_processed_tk()
    test_repair_inbox_bot_only_inbox_error()
    print("OK")
