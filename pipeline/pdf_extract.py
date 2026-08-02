#!/usr/bin/env python3
"""Extract lab results from Thuận Kiều PDF lab reports."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

# Order matters: count (#) before percent.
LAB_LINE_SPECS = [
    ("WBC", r"Leukocytes\s*\(?\s*WBC\s*\)?"),
    ("Neutrophils_count", r"Neutrophils\s*#"),
    ("Neutrophils_pct", r"Neutrophils(?!\s*#)"),
    ("Eosinophils_count", r"Eosinophils\s*#"),
    ("Eosinophils_pct", r"Eosinophils(?!\s*#)"),
    ("Monocytes_count", r"Monocytes\s*#"),
    ("Monocytes_pct", r"Monocytes(?!\s*#)"),
    ("Basophils_count", r"Basophils\s*#"),
    ("Basophils_pct", r"Basophils(?!\s*#)"),
    ("Lymphocytes_count", r"Lymphocytes\s*#"),
    ("Lymphocytes_pct", r"Lymphocytes(?!\s*#)"),
    ("RBC", r"Erythrocytes\s*\(?\s*RBC\s*\)?"),
    ("HGB", r"Hemoglobin\s*\(?\s*H(?:GB|b)\s*\)?"),
    ("HCT", r"Hematocrit(?:\s*\(?\s*Hct\s*\)?)?"),
    ("MCV", r"\bMCV\b"),
    ("MCHC", r"\bMCHC\b"),
    ("MCH", r"\bMCH\b"),
    ("RDW", r"\bRDW\b"),
    ("PLT", r"Platelets\s*\(?\s*PLT\s*\)?"),
    ("MPV", r"\bMPV\b"),
    ("Glucose", r"\bGlucose\b"),
    ("Urea", r"\bUrea\b"),
    ("Creatinine", r"\bCreatinine\b"),
    ("AST", r"AST\s*\(?\s*SGOT\s*\)?"),
    ("ALT", r"ALT\s*\(?\s*SGPT\s*\)?"),
]

URINE_SPECS = [
    ("Urobilinogen", r"Urobilinogen"),
    ("Glucose_NT", r"Glucose"),
    ("Ketone", r"Ketone"),
    ("Bilirubin_NT", r"Bilirubin"),
    ("Protein_NT", r"(?:Đạm|Protein)"),
    ("Nitrite", r"Nitrite"),
    ("pH_NT", r"\bpH\b"),
    ("Mau_NT", r"(?:Máu|Hồng cầu)"),
    ("Ti_trong", r"Tỉ\s*trọng"),
    ("Bach_cau_NT", r"Bạch\s*cầu"),
]

# Âm tính / Am tinh / Negative / (+) / bare number
_VAL_TOKEN = (
    r"(?P<val>\(\s*\+\s*\)|Âm\s*t[íi]nh|Am\s*tinh|Positive|Negative|"
    r"[<>]?\s*\d+(?:[.,]\d+)?)"
)
VALUE_RE = re.compile(
    rf"^{_VAL_TOKEN}\s*"
    r"(?:\([^)]*\))?\s*(?P<unit>[A-Za-z%μµ^0-9/.\-]*)",
    re.I,
)
_AM_TINH_RE = re.compile(r"âm\s*t[íi]nh|am\s*tinh", re.I)


def _norm_num(s: str) -> str:
    return s.replace(",", ".").strip()


def read_pdf_text(path: Path) -> str:
    with pdfplumber.open(str(path)) as pdf:
        parts = []
        for page in pdf.pages:
            t = page.extract_text() or ""
            parts.append(t)
    # Fix glued tokens like Neutrophils23.8
    text = "\n".join(parts)
    text = re.sub(r"(Neutrophils|Eosinophils|Monocytes|Basophils|Lymphocytes)(?=\d)", r"\1 ", text)
    return text


def parse_header(text: str) -> dict:
    info: dict = {
        "ho_ten": "",
        "nam_sinh": "",
        "gioi_tinh": "",
        "sid": "",
        "sdt": "",
        "dia_chi": "",
        "ngay_co_kq": "",
        "mau_kham": "",
    }
    m = re.search(
        r"Họ\s*tên:\s*(.+?)\s+Năm\s*sinh\s+(\d{4})\s+Giới\s*tính:\s*(\S+)",
        text,
        re.I,
    )
    if m:
        info["ho_ten"] = m.group(1).strip()
        info["nam_sinh"] = m.group(2)
        info["gioi_tinh"] = m.group(3).strip()
    m = re.search(r"SID:\s*(\S+)", text)
    if m:
        info["sid"] = m.group(1).rstrip("PID:")
    m = re.search(r"Số\s*ĐT:\s*([\d\s]+)", text)
    if m:
        info["sdt"] = re.sub(r"\s+", "", m.group(1))
    m = re.search(r"Địa\s*chỉ:\s*(.+?)\s+SID:", text)
    if m:
        info["dia_chi"] = m.group(1).strip()
    m = re.search(r"Ngày\s*có\s*kết\s*quả:\s*([0-9/: ]+)", text)
    if m:
        info["ngay_co_kq"] = m.group(1).strip()
    try:
        y = int(info["nam_sinh"])
        info["mau_kham"] = "M4" if y <= 1967 else "M3"
    except Exception:
        info["mau_kham"] = ""
    return info


def _split_sections(text: str) -> tuple[str, str, str]:
    """Return (huyet, sinhhoa, urine).

    Avoid false split on header text like 'Loại mẫu: Máu/Nước tiểu'.
    """
    urine = ""
    body = text
    m_urine = re.search(r"(?m)^(Nước\s*tiểu)\b", text, re.I)
    if not m_urine:
        m_urine = re.search(r"\n\s*(Nước\s*tiểu)\b", text, re.I)
    if m_urine:
        body, urine = text[: m_urine.start()], text[m_urine.start() :]

    m_chem = re.search(r"(?m)^(Sinh\s*hoá|Sinh\s*hóa)\b", body, re.I)
    if not m_chem:
        m_chem = re.search(r"\n\s*(Sinh\s*hoá|Sinh\s*hóa)\b", body, re.I)
    if m_chem:
        huyet, sinhhoa = body[: m_chem.start()], body[m_chem.start() :]
    else:
        huyet, sinhhoa = body, ""
    return huyet, sinhhoa, urine


def _parse_lab_line(line: str, name_pat: str) -> tuple[str, str] | None:
    m = re.search(name_pat + r"\s*(.+)$", line, re.I)
    if not m:
        return None
    rest = m.group(1).strip()
    # Prefer number / Am tinh / (+)
    vm = re.match(
        rf"^{_VAL_TOKEN}\s*(?:\([^)]*\))?\s*(?P<unit>.*)$",
        rest,
        re.I,
    )
    if not vm:
        # value may appear before unit words stuck together
        vm2 = re.search(
            r"(?P<val>\(\s*\+\s*\)|Âm\s*t[íi]nh|Am\s*tinh|Negative|[<>]?\d+(?:[.,]\d+)?)",
            rest,
            re.I,
        )
        if not vm2:
            return None
        val = re.sub(r"\s+", " ", vm2.group("val")).strip()
        unit = ""
    else:
        val = re.sub(r"\s+", " ", vm.group("val")).strip()
        unit = (vm.group("unit") or "").strip().split()[0] if (vm.group("unit") or "").strip() else ""
    if re.fullmatch(r"[<>]?\d+(?:[.,]\d+)?", val):
        val = _norm_num(val.lstrip("<>")) if not val.startswith(("<", ">")) else val[0] + _norm_num(val[1:])
    return val, unit


def _find_lab_in_text(section: str, pat: str) -> tuple[str, str] | None:
    for line in section.splitlines():
        if re.search(pat, line, re.I):
            got = _parse_lab_line(line, pat)
            if got:
                return got
    return None


def parse_labs(text: str) -> dict:
    huyet, sinhhoa, urine = _split_sections(text)
    labs: dict = {}

    # Blood count from huyet section
    for key, pat in LAB_LINE_SPECS:
        if key in ("Glucose", "Urea", "Creatinine", "AST", "ALT"):
            continue
        got = _find_lab_in_text(huyet, pat)
        if got:
            labs[key] = {"value_raw": got[0], "unit_raw": got[1]}

    # Chemistry — prefer sinhhoa; fall back to full body (minus urine) if missing
    chem_body = sinhhoa if sinhhoa.strip() else huyet
    chem_fallback = huyet + "\n" + sinhhoa
    for key, pat in [
        ("Glucose", r"(?:\bGlucose\b|Đường\s*(?:huyết|máu)|Duong\s*(?:huyet|mau)|Blood\s*sugar)"),
        ("Urea", r"(?:\bUrea\b|\bBUN\b|Urê|Ure(?:a)?\b)"),
        ("Creatinine", r"(?:\bCreatinine\b|Creatinin)"),
        ("AST", r"AST\s*\(?\s*SGOT\s*\)?"),
        ("ALT", r"ALT\s*\(?\s*SGPT\s*\)?"),
    ]:
        got = _find_lab_in_text(chem_body, pat) or _find_lab_in_text(chem_fallback, pat)
        if got:
            labs[key] = {"value_raw": got[0], "unit_raw": got[1]}

    # Urine
    for key, pat in URINE_SPECS:
        got = _find_lab_in_text(urine, pat)
        if got:
            labs[key] = {"value_raw": got[0], "unit_raw": got[1]}

    # Fallbacks when section split misses a line (common for Urobilinogen / Urea)
    full_for_urine = urine if urine.strip() else text
    if "Urobilinogen" not in labs:
        got = _find_lab_in_text(full_for_urine, r"Urobilinogen") or _find_lab_in_text(
            text, r"Urobilinogen"
        )
        if got:
            labs["Urobilinogen"] = {"value_raw": got[0], "unit_raw": got[1]}
    if "Urea" not in labs:
        got = _find_lab_in_text(text, r"(?:\bUrea\b|\bBUN\b|Urê|Ure(?:a)?\b)")
        if got:
            labs["Urea"] = {"value_raw": got[0], "unit_raw": got[1]}
    return labs


def normalize_for_web(labs: dict) -> dict:
    """Normalize units toward common Medinet SI-style targets.

    Targets (best-effort):
      WBC/PLT/counts: G/L (=10^9/L)
      RBC: T/L (=10^12/L)
      HGB: g/L
      HCT: L/L
      MCHC: g/L
      Glucose: mmol/L
      Creatinine: mcmol/L
      Urine Am tinh -> Negative
    """
    out = {}
    for key, item in labs.items():
        val = item.get("value_raw", "")
        unit = (item.get("unit_raw") or "").strip()
        note = ""
        vnorm, unorm = val, unit

        # Urine qualitative — web TextBox only accepts number or exact "Negative"
        if key == "Urobilinogen":
            if _AM_TINH_RE.search(str(val)) or re.fullmatch(r"negative|neg", str(val), re.I):
                vnorm, unorm, note = "Negative", "", "map Âm tính→Negative"
            elif re.search(r"\(\s*\+\s*\)", str(val)) or re.search(
                r"d[uư][ơo]ng\s*t[íi]nh|positive", str(val), re.I
            ):
                vnorm, unorm, note = "", unit, "dương tính qualitative — bỏ qua"
            else:
                try:
                    num = float(_norm_num(re.sub(r"^[<>]", "", str(val))))
                except Exception:
                    num = None
                if num is None:
                    vnorm, unorm, note = val, unit, "urobilinogen non-numeric"
                else:
                    u = unit.replace("μ", "u").replace("µ", "u").lower()
                    # Web field đơn vị µmol/L. PDF đôi khi ghi mg/dL (vd 0.2 → 3.38).
                    if "mg" in u or "ehrlich" in u:
                        num = num * 16.93
                        note = "Urobilinogen mg/dL×16.93→µmol/L"
                    elif ("umol" in u or "µmol" in u) or "mmol" in u:
                        note = "Urobilinogen giữ µmol/L"
                    elif 0 < num < 1.0:
                        # Giá trị nhỏ không ghi đơn vị: thường là mg/dL trên máy TK
                        num = num * 16.93
                        note = "Urobilinogen heuristic <1 → coi mg/dL×16.93→µmol/L"
                    else:
                        note = "Urobilinogen số → µmol/L"
                    vnorm = f"{round(num, 2):g}"
                    unorm = "µmol/L"
            out[key] = {
                "value_raw": val,
                "unit_raw": unit,
                "value_web": vnorm,
                "unit_web": unorm,
                "convert_note": note,
            }
            continue

        if key.endswith("_NT") or key in (
            "Ketone",
            "Nitrite",
            "Mau_NT",
            "Bach_cau_NT",
            "Glucose_NT",
            "Protein_NT",
            "Bilirubin_NT",
            "Ti_trong",
            "pH_NT",
        ):
            if _AM_TINH_RE.search(str(val)) or re.fullmatch(r"negative|neg", str(val), re.I):
                # PDF 'Âm tính' == web exact 'Negative'
                vnorm, unorm, note = "Negative", "", "map Âm tính→Negative"
            elif re.search(r"\(\s*\+\s*\)", str(val)) or re.search(
                r"d[uư][ơo]ng\s*t[íi]nh|positive", str(val), re.I
            ):
                # Do not send "( + )" — Medinet rejects it. Leave blank for import skip.
                vnorm, unorm, note = "", unit, "dương tính qualitative — bỏ qua (web chỉ nhận số/Negative)"
            else:
                # numeric urine (pH, tỉ trọng, concentrations)
                vnorm, unorm, note = val, unit, ""
            out[key] = {
                "value_raw": val,
                "unit_raw": unit,
                "value_web": vnorm,
                "unit_web": unorm,
                "convert_note": note,
            }
            continue

        try:
            num = float(_norm_num(re.sub(r"^[<>]", "", str(val))))
            prefix = val[0] if str(val)[:1] in "<>" else ""
        except Exception:
            out[key] = {
                "value_raw": val,
                "unit_raw": unit,
                "value_web": val,
                "unit_web": unit,
                "convert_note": "non-numeric",
            }
            continue

        u = unit.replace("μ", "u").replace("µ", "u").lower()

        if key in {
            "WBC",
            "PLT",
            "Neutrophils_count",
            "Eosinophils_count",
            "Monocytes_count",
            "Basophils_count",
            "Lymphocytes_count",
        }:
            if "10^9" in u or u in {"g/l", "g\\l"}:
                vnorm, unorm, note = f"{prefix}{num:g}", "G/L", "10^9/L≡G/L" if "10^9" in u else ""
            else:
                vnorm, unorm = f"{prefix}{num:g}", unit or "G/L"

        elif key == "RBC":
            if "10^12" in u:
                vnorm, unorm, note = f"{prefix}{num:g}", "T/L", "10^12/L≡T/L"
            else:
                vnorm, unorm = f"{prefix}{num:g}", unit or "T/L"

        elif key == "HGB":
            if "g/dl" in u:
                vnorm, unorm, note = f"{prefix}{num * 10:g}", "g/L", "g/dL×10→g/L"
            else:
                vnorm, unorm = f"{prefix}{num:g}", unit or "g/L"

        elif key == "HCT":
            if "%" in u or u == "":
                # if value looks like percent (>1) convert
                if num > 1.5:
                    vnorm, unorm, note = f"{prefix}{num / 100:g}", "L/L", "% /100 → L/L"
                else:
                    vnorm, unorm = f"{prefix}{num:g}", "L/L"
            else:
                vnorm, unorm = f"{prefix}{num:g}", unit or "L/L"

        elif key == "MCHC":
            if "g/dl" in u:
                vnorm, unorm, note = f"{prefix}{num * 10:g}", "g/L", "g/dL×10→g/L"
            else:
                vnorm, unorm = f"{prefix}{num:g}", unit or "g/L"

        elif key == "Glucose":
            if "mg/dl" in u or "mg%" in u:
                vnorm, unorm, note = f"{prefix}{num / 18.0:.2f}", "mmol/L", "mg/dL /18 → mmol/L"
            else:
                vnorm, unorm = f"{prefix}{num:g}", unit or "mmol/L"

        elif key == "Creatinine":
            if "mg" in u:
                # mg/dL * 88.4 ≈ umol/L
                vnorm, unorm, note = f"{prefix}{num * 88.4:.2f}", "mcmol/L", "mg%×88.4→mcmol/L"
            else:
                vnorm, unorm = f"{prefix}{num:g}", unit or "mcmol/L"

        elif key == "Urea":
            # keep; web unit unclear — expose both
            vnorm, unorm, note = f"{prefix}{num:g}", unit, "giữ nguyên — kiểm tra đơn vị web"

        else:
            vnorm, unorm = f"{prefix}{num:g}", unit

        out[key] = {
            "value_raw": val,
            "unit_raw": unit,
            "value_web": vnorm,
            "unit_web": unorm,
            "convert_note": note,
        }
    return out


def extract_pdf(path: Path) -> dict:
    text = read_pdf_text(path)
    header = parse_header(text)
    labs_raw = parse_labs(text)
    labs = normalize_for_web(labs_raw)
    return {
        "source_file": str(path),
        "file_name": path.name,
        **header,
        "labs": labs,
        "parse_ok": bool(header.get("ho_ten") and labs),
    }
