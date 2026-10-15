"""Unit tests for Vietnamese hourly Drive report."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from bao_cao_gio import (  # noqa: E402
    _parse_move_line,
    build_report_text,
    write_hourly_report,
)


def test_parse_move_and_vietnamese():
    m = _parse_move_line("PROCESSED\tNGUYEN VAN A\tmau.pdf\t->\tPROCESSED/mau.pdf")
    assert m["tag"] == "PROCESSED"
    assert m["ho_ten"] == "NGUYEN VAN A"
    assert "PROCESSED" in m["dest"]
    assert "điền" in m["giai_thich"].lower() or "Đã" in m["giai_thich"]


def test_write_to_env_dir(tmp_path: Path | None = None):
    root = Path(os.environ.get("PKDK_BAO_CAO_DIR") or "")
    if not root or not root.exists():
        # pytest-less fallback
        import tempfile

        root = Path(tempfile.mkdtemp(prefix="bao_cao_"))
        os.environ["PKDK_BAO_CAO_DIR"] = str(root)
    text = build_report_text(
        mode="hourly",
        bot_role="inbox",
        summary={"imported": 1, "moved_missing": 0, "results": 1, "new_files": 1},
        moves=["NO_TTHC\tB\tx.pdf\t->\tMISSING/x.pdf"],
        results=[],
        counts0={"inbox": 2, "missing": 1, "error": 0, "processed": 0},
        counts1={"inbox": 1, "missing": 2, "error": 0, "processed": 0},
        accounts=["pkdkthuankieu"],
    )
    assert "BÁO CÁO GIỜ" in text
    assert "MISSING" in text
    assert "di chuyển" in text.lower() or "Di chuyển" in text or "chuyển" in text
    paths = write_hourly_report(
        mode="hourly",
        bot_role="inbox",
        summary={"imported": 0, "results": 0, "new_files": 0},
        moves=[],
        results=[],
        counts0={"inbox": 0, "missing": 0, "error": 0, "processed": 0},
        counts1={"inbox": 0, "missing": 0, "error": 0, "processed": 0},
    )
    assert paths
    latest = root / "MOI_NHAT.txt"
    assert latest.exists()
    body = latest.read_text(encoding="utf-8")
    assert "BÁO CÁO GIỜ" in body


if __name__ == "__main__":
    test_parse_move_and_vietnamese()
    test_write_to_env_dir()
    print("OK bao_cao_gio")
