"""Repair/full scan dirs must include TK1/TK2; NEVER walk MISSING on G:."""
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


def test_full_scan_missing_bot_no_missing_walk():
    """full+repair must NOT rglob MISSING (Drive hang overnight)."""
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
        assert "MISSING" not in names
        assert "TK1" in names
        assert "TK2" in names
        assert "PROCESSED" in names


def test_full_scan_all_excludes_missing():
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
        for must in ("INBOX_CLS", "ERROR", "PROCESSED", "UNDER 18", "TK1", "TK2"):
            assert must in names, f"full-scan all missing {must}: {names}"
        assert "MISSING" not in names
        assert not any(n.startswith("MISSING") for n in names)


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


def test_name_digest_no_file_open():
    from hourly_sync import name_digest

    p = Path("/nonexistent/drive/MISSING/foo.pdf")
    d = name_digest(p)
    assert d.startswith("name:")
    assert len(d) > 20


def test_seed_missing_scandir():
    from hourly_sync import seed_missing_names_fast

    with tempfile.TemporaryDirectory() as td:
        miss = Path(td) / "MISSING"
        miss.mkdir()
        for i in range(5):
            (miss / f"a{i}.pdf").write_bytes(b"%PDF")
        rows: list[dict] = []
        n = seed_missing_names_fast(miss, rows, budget=3)
        assert n == 3
        assert len(rows) == 3
        assert all(r["status"] == "WAITING_ADMIN" for r in rows)
        assert all(str(r["file_hash"]).startswith("name:") for r in rows)


if __name__ == "__main__":
    test_repair_all_includes_tk1_tk2_not_missing()
    test_repair_missing_bot_fillable_only()
    test_full_scan_missing_bot_no_missing_walk()
    test_repair_requeues_imported_via_status_gate()
    test_full_scan_all_excludes_missing()
    test_repair_inbox_bot_only_inbox_error()
    test_name_digest_no_file_open()
    test_seed_missing_scandir()
    print("OK")
