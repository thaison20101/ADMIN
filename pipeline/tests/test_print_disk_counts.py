"""DISK inventory must count TK1/TK2 even when cases.csv is empty."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))


def test_disk_counts_sees_tk_folders(monkeypatch=None):
    from print_disk_counts import disk_counts

    with tempfile.TemporaryDirectory() as td:
        sync = Path(td) / "sync"
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
        (sync / "ERROR" / "a.pdf").write_bytes(b"%PDF")
        (sync / "PROCESSED" / "b.pdf").write_bytes(b"%PDF")
        (sync / "TK1" / "c.pdf").write_bytes(b"%PDF")
        (sync / "TK1" / "d.pdf").write_bytes(b"%PDF")
        (sync / "TK2" / "e.pdf").write_bytes(b"%PDF")
        c = disk_counts(sync)
        assert c["error"] == 1
        assert c["processed"] == 1
        assert c["tk1"] == 2
        assert c["tk2"] == 1
        assert c["inbox"] == 0


def test_restore_skips_when_ledger_populated():
    from restore_cases_snapshot import _row_count

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cases.csv"
        p.write_text(
            "case_key,source_file\n"
            + "\n".join(f"k{i},f{i}.pdf" for i in range(15)),
            encoding="utf-8",
        )
        assert _row_count(p) == 15


if __name__ == "__main__":
    test_disk_counts_sees_tk_folders()
    test_restore_skips_when_ledger_populated()
    print("OK")
