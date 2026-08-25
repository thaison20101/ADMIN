"""Regression: mọi kết quả PDF (trong/ngoài khoảng) phải parse được — không nhầm biên khoảng."""

from __future__ import annotations

import sys
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from pdf_extract import (  # noqa: E402
    _parse_lab_line,
    _unglue_lab_text,
    _value_from_row_cells,
    normalize_for_web,
    parse_labs,
)


def test_mchc_rdw_in_and_out_of_range_layouts():
    cases = [
        (r"\bMCHC\b", "MCHC 289 ( 320 - 360 ) g/L", "289"),
        (r"\bMCHC\b", "MCHC ( 320 - 360 ) g/L 289", "289"),
        (r"\bMCHC\b", "MCHC 320 - 360 289 g/L", "289"),
        (r"\bRDW\b", "RDW 10.8 ( 11.5 - 14.5 ) %", "10.8"),
        (r"\bRDW\b", "RDW ( 11.5 - 14.5 ) % 10.8", "10.8"),
        (r"\bMCV\b", "MCV ( 80.0 - 99.0 ) fL 76.7", "76.7"),
        (r"\bMCV\b", "MCV 94.1 ( 80.0 - 99.0 ) fL", "94.1"),
        (r"Monocytes\s*#", "Monocytes # ( 0.2 - 0.8 ) G/L 0.801", "0.801"),
        (r"Basophils\s*#", "Basophils # 0.313 ( 0.0 - 0.1 ) G/L", "0.313"),
    ]
    for pat, line, expect in cases:
        got = _parse_lab_line(line, pat)
        assert got is not None, f"miss: {line}"
        assert got[0] == expect, f"{line} -> {got[0]} want {expect}"
        # Must NOT return reference bounds
        assert got[0] not in {
            "320",
            "360",
            "11.5",
            "14.5",
            "80.0",
            "99.0",
            "0.0",
            "0.1",
            "0.2",
            "0.8",
        }


def test_right_shift_leftover_bounds_and_glued():
    """Ghi chú layout: leftover bounds without dash, or Name glued to value."""
    cases = [
        (r"\bMCV\b", "MCV 80.0 99.0 70.0", "70.0"),
        (r"\bMCHC\b", "MCHC 320 360 255", "255"),
        (r"\bMCV\b", "MCV70.0 ( 80.0 - 99.0 ) fL", "70.0"),
        (r"\bMCHC\b", "MCHC289 ( 320 - 360 ) g/L", "289"),
        (r"\bMCH(?!C)\b", "MCH17.9 ( 27.0 - 33.0 ) pg", "17.9"),
        (
            r"Hemoglobin\s*\(?\s*H(?:GB|b)\s*\)?",
            "Hemoglobin (Hb)102 ( 115 - 150 ) g/L",
            "102",
        ),
        (r"\bRDW\b", "RDW ( 11.5 - 14.5 ) % 10.8", "10.8"),
    ]
    for pat, line, expect in cases:
        got = _parse_lab_line(_unglue_lab_text(line), pat)
        assert got is not None, f"miss: {line}"
        assert got[0] == expect, f"{line} -> {got[0]} want {expect}"


def test_table_row_ghi_chu_cell():
    """Table cells: empty Kết quả, value in Ghi chú column."""
    row = ["MCV", "", "70.0", "( 80.0 - 99.0 )", "fL"]
    got = _value_from_row_cells(row)
    assert got is not None
    assert got[0] == "70.0"
    row2 = ["Urobilinogen", "Âm tính", "", "( Âm tính )", ""]
    got2 = _value_from_row_cells(row2)
    assert got2 is not None
    assert "âm" in got2[0].lower() or "am" in got2[0].lower()


def test_parse_labs_blood_and_urine_together():
    text = """
Họ tên: NGUYEN THI THANH THUY
Năm sinh: 1985
Huyết học Công thức máu
Leukocytes (WBC) 6.2 ( 4.01 - 11.42 ) G/L
Erythrocytes (RBC) 4.5 ( 4.01 - 5.79 ) T/L
Hemoglobin (Hb) 120 ( 115 - 150 ) g/L
MCV ( 80.0 - 99.0 ) fL 70.0
MCH ( 27.0 - 33.0 ) pg 17.9
MCHC ( 320 - 360 ) g/L 255
RDW ( 11.5 - 14.5 ) % 10.8
Platelets (PLT) 250 ( 146 - 429 ) G/L
Sinh hóa
Glucose 5.02 ( 3.9 - 6.4 ) mmol/L
Creatinine 66.3 ( 62 - 106 ) umol/L
AST (SGOT) 25.06 ( 0 - 40 ) U/L
ALT (SGPT) 17.76 ( 0 - 41 ) U/L
Nước tiểu
Urobilinogen Âm tính
Glucose Âm tính
Ketone Âm tính
Bilirubin Âm tính
Protein Âm tính
Nitrite Âm tính
pH 6.0
Máu Âm tính
Tỉ trọng 1.015
Bạch cầu Âm tính
"""
    labs = parse_labs(text)
    norm = normalize_for_web(labs)
    assert (norm.get("MCV") or {}).get("value_web") == "70"
    assert (norm.get("MCH") or {}).get("value_web") == "17.9"
    assert (norm.get("MCHC") or {}).get("value_web") == "255"
    assert (norm.get("RDW") or {}).get("value_web") == "10.8"
    assert (norm.get("Urobilinogen") or {}).get("value_web") == "Negative"
    assert (norm.get("Glucose_NT") or {}).get("value_web") == "Negative"
    assert (norm.get("Ketone") or {}).get("value_web") == "Negative"
    assert (norm.get("pH_NT") or {}).get("value_web") in {"6", "6.0"}
    assert str((norm.get("Ti_trong") or {}).get("value_web") or "").startswith("1.01")
    from medinet_api import labs_to_form_payload

    payload = labs_to_form_payload(norm, phieukham_id=1, gioi_tinh="Nữ")
    assert payload.get("XNM_MCV") == 70
    assert payload.get("XNM_MCHC") == 255
    assert payload.get("NuocTieu_Urobilinogen") == "Negative"
    assert payload.get("NuocTieu_Duong") == "Negative"
    assert payload.get("NuocTieu_pH") in {6, 6.0}


def test_parse_labs_khoa_like_block():
    text = """
Họ tên: NGUYEN HUU KHOA
Năm sinh: 1957
Huyết học Công thức máu
Leukocytes (WBC) 8.85 ( 4.01 - 11.42 ) G/L
Neutrophils 43.5 ( 40 - 74 ) %
Neutrophils # 3.85 ( 1.7 - 7.5 ) G/L
Monocytes 9.05 ( 3.4 - 9.0 ) %
Monocytes # 0.801 ( 0.2 - 0.8 ) G/L
Basophils 3.54 ( 0.0 - 1.5 ) %
Basophils # 0.313 ( 0.0 - 0.1 ) G/L
Lymphocytes 43.3 ( 19 - 48 ) %
Lymphocytes # 3.83 ( 1.0 - 4.0 ) G/L
Erythrocytes (RBC) 5.14 ( 4.01 - 5.79 ) T/L
Hemoglobin (Hb) 140 ( 115 - 150 ) g/L
Hematocrit (Hct) 0.48 ( 0.34 - 0.49 ) L/L
MCV 94.1 ( 80.0 - 99.0 ) fL
MCH 27.2 ( 27.0 - 33.0 ) pg
MCHC 289 ( 320 - 360 ) g/L
RDW 10.8 ( 11.5 - 14.5 ) %
Platelets (PLT) 213 ( 146 - 429 ) G/L
Sinh hóa
Glucose 4.76 ( 3.9 - 6.4 ) mmol/L
Creatinine 86.63 ( 62 - 106 ) umol/L
AST (SGOT) 78.54 ( 0 - 40 ) U/L
ALT (SGPT) 56.99 ( 0 - 41 ) U/L
"""
    labs = parse_labs(text)
    norm = normalize_for_web(labs)
    assert (norm.get("MCHC") or {}).get("value_web") == "289"
    assert (norm.get("RDW") or {}).get("value_web") == "10.8"
    assert (norm.get("Basophils_count") or {}).get("value_web") == "0.313"
    assert (norm.get("Monocytes_count") or {}).get("value_web") == "0.801"
    assert (norm.get("AST") or {}).get("value_web") == "78.54"


def test_labs_to_form_includes_out_of_range():
    from medinet_api import labs_to_form_payload

    labs = normalize_for_web(
        {
            "MCHC": {"value_raw": "289", "unit_raw": "g/L"},
            "RDW": {"value_raw": "10.8", "unit_raw": "%"},
            "RBC": {"value_raw": "5.14", "unit_raw": "T/L"},
        }
    )
    payload = labs_to_form_payload(labs, phieukham_id=1, gioi_tinh="Nam")
    assert payload.get("XNM_MCHC") == 289
    assert payload.get("XNM_RDW") == 10.8
    assert payload.get("CongThucMau_SLHC") == 5.14


def test_parse_labs_quy_out_of_range_block():
    """NGUYEN HUU QUY-like: MCV/MCH/MCHC outside ref — must still parse."""
    text = """
Họ tên: NGUYEN HUU QUY
Năm sinh: 1961
Huyết học Công thức máu
Leukocytes (WBC) 8.35 ( 4.01 - 11.42 ) G/L
Neutrophils 20.7 ( 40 - 74 ) %
Neutrophils # 1.73 ( 1.7 - 7.5 ) G/L
Monocytes 13.3 ( 3.4 - 9.0 ) %
Monocytes # 1.11 ( 0.2 - 0.8 ) G/L
Basophils 10.5 ( 0.0 - 1.5 ) %
Basophils # 0.881 ( 0.0 - 0.1 ) G/L
Lymphocytes 54.5 ( 19 - 48 ) %
Lymphocytes # 4.55 ( 1.0 - 4.0 ) G/L
Erythrocytes (RBC) 6.34 ( 4.01 - 5.79 ) T/L
Hemoglobin (Hb) 113 ( 115 - 150 ) g/L
Hematocrit (Hct) 0.44 ( 0.34 - 0.49 ) L/L
MCV 70.0 ( 80.0 - 99.0 ) fL
MCH 17.9 ( 27.0 - 33.0 ) pg
MCHC 255 ( 320 - 360 ) g/L
RDW 11.8 ( 11.5 - 14.5 ) %
Platelets (PLT) 330 ( 146 - 429 ) G/L
Sinh hóa
Glucose 5.02 ( 3.9 - 6.4 ) mmol/L
Creatinine 66.3 ( 62 - 106 ) umol/L
AST (SGOT) 25.06 ( 0 - 40 ) U/L
ALT (SGPT) 17.76 ( 0 - 41 ) U/L
"""
    labs = parse_labs(text)
    norm = normalize_for_web(labs)
    assert (norm.get("MCV") or {}).get("value_web") == "70"
    assert (norm.get("MCH") or {}).get("value_web") == "17.9"
    assert (norm.get("MCHC") or {}).get("value_web") == "255"
    assert (norm.get("RDW") or {}).get("value_web") == "11.8"
    assert (norm.get("RBC") or {}).get("value_web") == "6.34"
    assert (norm.get("HGB") or {}).get("value_web") == "113"
    assert (norm.get("Basophils_count") or {}).get("value_web") == "0.881"
    from medinet_api import labs_to_form_payload

    payload = labs_to_form_payload(norm, phieukham_id=1, gioi_tinh="Nam")
    assert payload.get("XNM_MCV") == 70
    assert payload.get("XNM_MCH") == 17.9
    assert payload.get("XNM_MCHC") == 255
    assert payload.get("XNM_RDW") == 11.8
    assert payload.get("CongThucMau_SLHC") == 6.34


def test_ghi_chu_after_ref_all_core_fields():
    cases = [
        (r"\bMCV\b", "MCV ( 80.0 - 99.0 ) fL 70.0", "70.0"),
        (r"\bMCH\b", "MCH ( 27.0 - 33.0 ) pg 17.9", "17.9"),
        (r"\bMCHC\b", "MCHC ( 320 - 360 ) g/L 255", "255"),
        (
            r"Erythrocytes\s*\(?\s*RBC\s*\)?",
            "Erythrocytes (RBC) ( 4.01 - 5.79 ) T/L 6.34",
            "6.34",
        ),
        (
            r"Hemoglobin\s*\(?\s*H(?:GB|b)\s*\)?",
            "Hemoglobin (Hb) ( 115 - 150 ) g/L 113",
            "113",
        ),
        (r"Basophils\s*#", "Basophils # ( 0.0 - 0.1 ) G/L 0.881", "0.881"),
        (r"Monocytes\s*#", "Monocytes # ( 0.2 - 0.8 ) G/L 1.11", "1.11"),
        (r"AST\s*\(?\s*SGOT\s*\)?", "AST (SGOT) ( 0 - 40 ) U/L 25.06", "25.06"),
    ]
    for pat, line, expect in cases:
        got = _parse_lab_line(line, pat)
        assert got is not None, f"miss: {line}"
        assert got[0] == expect, f"{line} -> {got[0]} want {expect}"


if __name__ == "__main__":
    test_mchc_rdw_in_and_out_of_range_layouts()
    test_right_shift_leftover_bounds_and_glued()
    test_table_row_ghi_chu_cell()
    test_parse_labs_blood_and_urine_together()
    test_parse_labs_khoa_like_block()
    test_labs_to_form_includes_out_of_range()
    test_parse_labs_quy_out_of_range_block()
    test_ghi_chu_after_ref_all_core_fields()
    print("OK")
