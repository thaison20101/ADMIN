"""CCCD match with wrong name still READY_IMPORT + name_mismatch."""
from __future__ import annotations

import sys
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from tthc_match import resolve_tthc_matches  # noqa: E402


def test_cccd_name_mismatch_allows_fill():
    idx = {
        "by_fold_year": {},
        "by_name_year": {},
        "by_cccd": {
            "079087013411": [
                {
                    "HoTen": "NGUYEN VAN A",
                    "CCCD": "079087013411",
                    "phieukhamId": 99,
                    "_medinet_account": "pkdkthuankieu",
                    "NgaySinh": "1987-01-28",
                }
            ]
        },
    }
    row = {"ho_ten": "VONG QUOC CHU", "cccd": "079087013411", "nam_sinh": "1987"}
    r = resolve_tthc_matches(row, idx, accounts=[{"id": "pkdkthuankieu"}])
    assert r.status == "READY_IMPORT"
    assert r.name_mismatch is True
    assert r.matches[0]["phieukhamId"] == 99
    assert "cccd" in r.mode


def test_glucose_fasting_and_random():
    from pdf_extract import parse_labs
    from medinet_api import labs_to_form_payload

    text = """
Sinh hóa máu
Glucose 4.63 ( 3.9 - 6.4 ) mmol/L
Đường máu lúc đói 5.10 ( 3.9 - 6.1 ) mmol/L
Urea 5.0 ( 2.5 - 7.5 ) mmol/L
"""
    labs = parse_labs(text)
    # At least one glucose mapped
    assert "Glucose" in labs or "Glucose_fasting" in labs
    payload = labs_to_form_payload(labs, phieukham_id=1, gioi_tinh="Nam")
    assert payload.get("LoaiKham") == 5152
    assert "SinhHoaMau_DuongMau" in payload or "SinhHoaMau_DuongMauLucDoi" in payload


if __name__ == "__main__":
    test_cccd_name_mismatch_allows_fill()
    test_glucose_fasting_and_random()
    print("OK")
