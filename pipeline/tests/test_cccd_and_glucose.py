"""CCCD match + glucose bat ky / luc doi mapping."""
from __future__ import annotations

import sys
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from medinet_api import labs_to_form_payload  # noqa: E402
from pdf_extract import normalize_for_web, parse_labs  # noqa: E402
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


def test_name_year_no_cccd_ready():
    """Lab PDF often has no CCCD in text — name+year still matches."""
    idx = {
        "by_fold_year": {
            "VONG QUOC CHU|1987": [
                {
                    "HoTen": "VÒNG QUỐC CHỦ",
                    "CCCD": "079087013411",
                    "phieukhamId": 42,
                    "_medinet_account": "pkdkthuankieu",
                    "NgaySinh": "1987-01-28",
                }
            ]
        },
        "by_name_year": {},
        "by_cccd": {},
    }
    row = {"ho_ten": "VONG QUOC CHU", "cccd": "", "nam_sinh": "1987"}
    r = resolve_tthc_matches(
        row, idx, accounts=[{"id": "pkdkthuankieu"}, {"id": "pkdk_Thuankieu"}]
    )
    assert r.status == "READY_IMPORT"
    assert r.name_mismatch is False
    assert r.matches[0]["phieukhamId"] == 42


def test_no_tthc_waiting_admin():
    idx = {"by_fold_year": {}, "by_name_year": {}, "by_cccd": {}}
    row = {"ho_ten": "NGUOI KHONG CO", "cccd": "", "nam_sinh": "1990"}
    r = resolve_tthc_matches(row, idx, accounts=[{"id": "pkdkthuankieu"}])
    assert r.status == "WAITING_ADMIN"
    assert r.matches == []


def _web(labs, key):
    item = labs.get(key) or {}
    return item.get("value_web") or item.get("value_raw")


def test_glucose_bat_ky_only_maps_random_field():
    """Old PDFs: 'Duong mau bat ky' -> SinhHoaMau_DuongMau only."""
    text = """
Sinh hóa máu
Đường máu bất kỳ 4.63 ( < 6.9 ) mmol/L
Creatinine 89.28 ( 53.0 - 106.1 ) mcmol/L
"""
    labs = normalize_for_web(parse_labs(text))
    assert _web(labs, "Glucose") in {"4.63", "4,63"} or float(
        str(_web(labs, "Glucose")).replace(",", ".")
    ) == 4.63
    assert "Glucose_fasting" not in labs
    payload = labs_to_form_payload(labs, phieukham_id=1, gioi_tinh="Nam")
    assert payload.get("SinhHoaMau_DuongMau") == 4.63
    assert "SinhHoaMau_DuongMauLucDoi" not in payload


def test_glucose_bat_ky_ascii_label():
    text = """
Sinh hoa mau
Duong mau bat ky 4.63 ( < 6.9 ) mmol/L
"""
    labs = normalize_for_web(parse_labs(text))
    assert "Glucose" in labs
    assert "Glucose_fasting" not in labs
    payload = labs_to_form_payload(labs, phieukham_id=1, gioi_tinh="Nam")
    assert payload.get("SinhHoaMau_DuongMau") == 4.63
    assert "SinhHoaMau_DuongMauLucDoi" not in payload


def test_glucose_luc_doi_only():
    text = """
Sinh hóa máu
Đường máu lúc đói 5.10 ( 3.9 - 6.1 ) mmol/L
"""
    labs = normalize_for_web(parse_labs(text))
    assert "Glucose_fasting" in labs
    assert "Glucose" not in labs
    payload = labs_to_form_payload(labs, phieukham_id=1, gioi_tinh="Nam")
    assert payload.get("SinhHoaMau_DuongMauLucDoi") == 5.1
    assert "SinhHoaMau_DuongMau" not in payload


def test_glucose_both_fields_no_cross_copy():
    text = """
Sinh hóa máu
Đường máu bất kỳ 4.63 ( < 6.9 ) mmol/L
Đường máu lúc đói 5.10 ( 3.9 - 6.1 ) mmol/L
"""
    labs = normalize_for_web(parse_labs(text))
    assert "Glucose" in labs
    assert "Glucose_fasting" in labs
    payload = labs_to_form_payload(labs, phieukham_id=1, gioi_tinh="Nam")
    assert payload.get("SinhHoaMau_DuongMau") == 4.63
    assert payload.get("SinhHoaMau_DuongMauLucDoi") == 5.1
    assert payload.get("LoaiKham") == 5152


def test_glucose_english_and_fasting():
    from pdf_extract import parse_labs as pl

    text = """
Sinh hóa máu
Glucose 4.63 ( 3.9 - 6.4 ) mmol/L
Đường máu lúc đói 5.10 ( 3.9 - 6.1 ) mmol/L
Urea 5.0 ( 2.5 - 7.5 ) mmol/L
"""
    labs = pl(text)
    assert "Glucose" in labs or "Glucose_fasting" in labs
    payload = labs_to_form_payload(labs, phieukham_id=1, gioi_tinh="Nam")
    assert payload.get("LoaiKham") == 5152
    assert "SinhHoaMau_DuongMau" in payload or "SinhHoaMau_DuongMauLucDoi" in payload


if __name__ == "__main__":
    test_cccd_name_mismatch_allows_fill()
    test_name_year_no_cccd_ready()
    test_no_tthc_waiting_admin()
    test_glucose_bat_ky_only_maps_random_field()
    test_glucose_bat_ky_ascii_label()
    test_glucose_luc_doi_only()
    test_glucose_both_fields_no_cross_copy()
    test_glucose_english_and_fasting()
    print("OK")
