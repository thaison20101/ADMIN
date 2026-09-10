"""refill_one_patient finds PDF by name even when CCCD absent in PDF text."""
from __future__ import annotations

import sys
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from refill_one_patient import (  # noqa: E402
    _score_candidate,
    fold_ascii,
    path_matches_name,
)


def test_fold_and_path_match():
    assert "VONG QUOC CHU" in fold_ascii("VÒNG QUỐC CHỦ")
    p = Path(r"G:/Drive/TK2/300826-497079 - VONG QUOC CHU - 1987 - M.pdf")
    assert path_matches_name(p, "VONG QUOC CHU")
    assert path_matches_name(p, "VÒNG QUỐC CHỦ")
    assert not path_matches_name(p, "NGUYEN VAN A")


def test_score_accepts_name_without_cccd_in_pdf():
    data = {
        "cccd": "",
        "ho_ten": "VÒNG QUỐC CHỦ",
        "nam_sinh": "1987",
    }
    pdf = Path("300826-497079 - VONG QUOC CHU - 1987 - M.pdf")
    sc = _score_candidate(pdf, data, "079087013411", "VONG QUOC CHU")
    assert sc >= 40


def test_score_rejects_wrong_cccd():
    data = {"cccd": "111111111111", "ho_ten": "VONG QUOC CHU", "nam_sinh": "1987"}
    pdf = Path("x - VONG QUOC CHU - 1987 - M.pdf")
    assert _score_candidate(pdf, data, "079087013411", "VONG QUOC CHU") < 0


if __name__ == "__main__":
    test_fold_and_path_match()
    test_score_accepts_name_without_cccd_in_pdf()
    test_score_rejects_wrong_cccd()
    print("OK")
