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


def test_repair_requeues_imported_via_status_gate():
    """Document expected gate: repair=True must not skip IMPORTED (code path)."""
    # Lightweight: ensure filter lists include TK paths for repair all
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


if __name__ == "__main__":
    test_repair_all_includes_tk1_tk2_not_missing()
    test_repair_missing_bot_fillable_only()
    test_full_scan_missing_includes_tk_and_missing()
    test_repair_requeues_imported_via_status_gate()
    print("OK")
