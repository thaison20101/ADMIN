"""Regression: mọi kết quả PDF (trong/ngoài khoảng) phải parse được — không nhầm biên khoảng."""

from __future__ import annotations

import sys
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from pdf_extract import _parse_lab_line, normalize_for_web, parse_labs  # noqa: E402


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
        assert got[0] not in {"320", "360", "11.5", "14.5", "80.0", "99.0", "0.0", "0.1", "0.2", "0.8"}


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


if __name__ == "__main__":
    test_mchc_rdw_in_and_out_of_range_layouts()
    test_parse_labs_khoa_like_block()
    test_labs_to_form_includes_out_of_range()
    print("OK")
