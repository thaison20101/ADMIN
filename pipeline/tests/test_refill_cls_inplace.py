"""Tests for refill_cls_inplace folder discovery (no Medinet / G:)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from refill_cls_inplace import find_priority_folder  # noqa: E402


def test_find_binh_tay_folder():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "PROCESSED").mkdir()
        (root / "MISSING").mkdir()
        target = root / "P. BÌNH TÂY - TRƯỜNG THCS NGUYỄN ĐỨC CẢNH - NGÀY 13-08-2026 - 165 CASE"
        target.mkdir()
        (target / "a.pdf").write_bytes(b"%PDF")
        found = find_priority_folder(root)
        assert found is not None
        assert found.name == target.name


def test_find_folder_ascii_fold():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "P. BINH TAY - TRUONG THCS NGUYEN DUC CANH - 13-08-2026 - 165 CASE").mkdir()
        found = find_priority_folder(root)
        assert found is not None
        assert "165 CASE" in found.name.upper()


if __name__ == "__main__":
    test_find_binh_tay_folder()
    test_find_folder_ascii_fold()
    print("OK")
