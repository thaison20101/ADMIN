#!/usr/bin/env python3
"""Extract lab results from Thuận Kiều PDF lab reports.

Important: values may sit in either:
  - column Kết quả (normal / in-range), OR
  - column Ghi chú (abnormal / out-of-range, often AFTER the reference interval)

Both must be read and sent to Medinet. Never skip a PDF field that exists.
Urea is optional when absent from the PDF.
"""

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
# PDF "Khoảng tham chiếu" e.g. ( 80.0 - 99.0 ) / (4.01-11.42)
# Strip so the TRUE result (in-range OR out-of-range) is never confused with bounds.
# Khoảng chỉ để bác sĩ xem — KHÔNG dùng để bỏ / skip chỉ số.
_REF_RANGE_RE = re.compile(
    r"\(\s*[<>]?\d+(?:[.,]\d+)?\s*[-–—]\s*[<>]?\d+(?:[.,]\d+)?\s*\)"
)
# Bare "low - high" without parens (some pdfplumber extractions)
_REF_RANGE_BARE_RE = re.compile(
    r"(?<![.\d])[<>]?\d+(?:[.,]\d+)?\s*[-–—]\s*[<>]?\d+(?:[.,]\d+)?(?![.\d])"
)
_NUM_RE = re.compile(r"[<>]?\d+(?:[.,]\d+)?")


def _norm_num(s: str) -> str:
    return s.replace(",", ".").strip()


def _strip_ref_ranges(s: str) -> str:
    """Remove reference intervals so the real result number remains.

    Never drop the lab value because it is outside the interval — khoảng tham chiếu
    is for doctors only. Both in-range and out-of-range results must be kept.
    """
    out = _REF_RANGE_RE.sub(" ", s or "")
    # Bare "low - high" only when a 3rd number (true result) is also on the line
    if len(list(_NUM_RE.finditer(out))) >= 3:
        out = _REF_RANGE_BARE_RE.sub(" ", out)
    return out


def _normalize_val_token(val: str) -> str:
    val = re.sub(r"\s+", " ", (val or "").strip())
    if re.fullmatch(r"[<>]?\d+(?:[.,]\d+)?", val):
        if val.startswith(("<", ">")):
            return val[0] + _norm_num(val[1:])
        return _norm_num(val)
    return val


def _extract_unit(text: str) -> str:
    """Pick a likely unit token from leftover text after the value."""
    if not text:
        return ""
    # Prefer common lab units
    m = re.search(
        r"(?i)\b(g/L|g/dL|G/L|T/L|fL|pg|mmol/L|mcmol/L|umol/L|µmol/L|%|L/L)\b",
        text,
    )
    if m:
        return m.group(1)
    parts = text.strip().split()
    return parts[0] if parts else ""


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
        "ngay_sinh": "",
        "gioi_tinh": "",
        "sid": "",
        "sdt": "",
        "dia_chi": "",
        "ngay_co_kq": "",
        "mau_kham": "",
        "cccd": "",
        "loai_mau": "",
        "chan_doan": "",
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
    m_dob = re.search(
        r"Ngày\s*sinh\s+(\d{1,2}/\d{1,2}/((?:19|20)\d{2}))",
        text,
        re.I,
    )
    if m_dob:
        info["ngay_sinh"] = m_dob.group(1).strip()
        if not info["nam_sinh"]:
            info["nam_sinh"] = m_dob.group(2)
        if not info["gioi_tinh"]:
            m_gt = re.search(r"Giới\s*tính:\s*(\S+)", text, re.I)
            if m_gt:
                info["gioi_tinh"] = m_gt.group(1).strip()
        if not info["ho_ten"]:
            m_ht = re.search(r"Họ\s*tên:\s*(.+?)(?:\s+Ngày\s*sinh|\s+Năm\s*sinh)", text, re.I)
            if m_ht:
                info["ho_ten"] = m_ht.group(1).strip()
    m = re.search(r"SID:\s*(\S+)", text)
    if m:
        info["sid"] = m.group(1).rstrip("PID:")
    m = re.search(r"Số\s*ĐT:\s*([.\d\s]+)", text)
    if m:
        raw_ph = m.group(1).strip()
        info["sdt"] = re.sub(r"\s+", "", raw_ph) if re.search(r"\d", raw_ph) else ""
    m = re.search(r"Địa\s*chỉ:\s*(.+?)\s+SID:", text)
    if m:
        info["dia_chi"] = m.group(1).strip()
    m = re.search(r"Ngày\s*có\s*kết\s*quả:\s*([0-9/: ]+)", text)
    if m:
        info["ngay_co_kq"] = m.group(1).strip()
    m = re.search(
        r"Chẩn\s*đoán:\s*(.+?)(?:\s+BS\s+chỉ|\s+Loại\s+mẫu|$)",
        text,
        re.I | re.S,
    )
    if m:
        info["chan_doan"] = m.group(1).strip()
        cm = re.search(r"CCCD:\s*(\d{9,12})", info["chan_doan"], re.I)
        if cm:
            info["cccd"] = cm.group(1)
    m = re.search(
        r"Loại\s*mẫu:\s*(.+?)(?:\s+Chất\s+lượng|\s+Đơn\s+vị|$)",
        text,
        re.I | re.S,
    )
    if m:
        info["loai_mau"] = m.group(1).strip()
    try:
        y = int(info["nam_sinh"])
        info["mau_kham"] = "M4" if y <= 1967 else "M3"
    except Exception:
        info["mau_kham"] = ""
    return info


def classify_sample_kind(header: dict, text: str = "") -> str:
    """BLOOD_URINE = standard CLS form; OTHER = e.g. Huyết Trắng → ERROR."""
    loai = str(header.get("loai_mau") or "")
    blob = f"{loai} {text[:800]}"
    if re.search(r"Huyết\s*Trắng|Huyet\s*Trang|dịch\s*âm\s*đạo", blob, re.I):
        return "OTHER"
    if re.search(r"Máu|Nước\s*tiểu|Mau/Nuoc", blob, re.I):
        return "BLOOD_URINE"
    if text and re.search(r"(?m)^(Nước\s*tiểu|Sinh\s*hoá|Huyết\s*đồ)\b", text, re.I):
        return "BLOOD_URINE"
    return "OTHER"


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
    """Parse `Name <value> [ref] [unit]` OR `Name [ref] [unit] <value>` (Ghi chú).

    Thuận Kiều PDFs put OUT-OF-RANGE results in column Ghi chú (often AFTER the
    reference interval). Old parser grabbed the first number inside (80.0-99.0)
    or failed → MCV/MCH/MCHC/Hb missing on web.
    """
    m = re.search(name_pat + r"\s*(.+)$", line, re.I)
    if not m:
        if re.search(name_pat + r"\s*$", line, re.I):
            return None
        return None
    rest = m.group(1).strip()
    if not rest:
        return None

    # Qualitative tokens first (urine)
    qm = re.match(
        r"^(?P<val>\(\s*\+\s*\)|Âm\s*t[íi]nh|Am\s*tinh|Positive|Negative)\b",
        rest,
        re.I,
    )
    if qm:
        return _normalize_val_token(qm.group("val")), ""

    # Strip reference ranges, then take the first remaining number (= true result).
    # Works for both:
    #   MCV 76.7 ( 80.0 - 99.0 ) fL
    #   MCV ( 80.0 - 99.0 ) fL 76.7   ← value in Ghi chú
    cleaned = _strip_ref_ranges(rest)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    nm = _NUM_RE.search(cleaned)
    if nm:
        val = _normalize_val_token(nm.group(0))
        after = cleaned[nm.end() :]
        before = cleaned[: nm.start()]
        unit = _extract_unit(after) or _extract_unit(before)
        return val, unit

    # No number outside refs → maybe only ref on this line (value on next line)
    return None


def _find_lab_in_text(section: str, pat: str) -> tuple[str, str] | None:
    lines = section.splitlines()
    for i, line in enumerate(lines):
        if not re.search(pat, line, re.I):
            continue
        got = _parse_lab_line(line, pat)
        if got:
            return got
        # Multiline: "MCV" / "MCV ( 80 - 99 ) fL" then next line "76.7"
        for j in range(1, 4):
            if i + j >= len(lines):
                break
            nxt = lines[i + j].strip()
            if not nxt:
                continue
            if re.search(
                r"(?i)^(?:Creatinine|Creatinin|AST|ALT|Urea|Ure|Urê|WBC|RBC|PLT|"
                r"Urobilinogen|Protein|Ketone|Bilirubin|Nitrite|pH|Leukocytes|"
                r"Erythrocytes|Hemoglobin|Hematocrit|Neutrophils|Lymphocytes|"
                r"Monocytes|Eosinophils|Basophils|MPV|RDW|MCV|MCHC|MCH|"
                r"Glucose|Platelets)\b",
                nxt,
            ):
                break
            # Skip pure reference-range / unit-only lines
            nxt_clean = _strip_ref_ranges(nxt)
            nxt_clean = re.sub(r"\s+", " ", nxt_clean).strip()
            if not nxt_clean or re.fullmatch(
                r"(?i)(?:g/L|g/dL|G/L|T/L|fL|pg|mmol/L|%|L/L|mcmol/L|umol/L|µmol/L)",
                nxt_clean,
            ):
                continue
            vm = re.match(
                rf"^{_VAL_TOKEN}\s*(?P<unit>[A-Za-z%μµ^0-9/.\-]*)",
                nxt_clean,
                re.I,
            )
            if vm:
                val = _normalize_val_token(vm.group("val"))
                unit = (vm.group("unit") or "").strip()
                return val, unit
            nm = _NUM_RE.search(nxt_clean)
            if nm:
                return _normalize_val_token(nm.group(0)), _extract_unit(
                    nxt_clean[nm.end() :]
                )
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
            # Blood Glucose must be numeric — ignore urine "Âm tính" if chem split failed
            if key == "Glucose" and not re.fullmatch(r"[<>]?\d+(?:[.,]\d+)?", str(got[0])):
                got = None
        if got:
            labs[key] = {"value_raw": got[0], "unit_raw": got[1]}

    # Explicit blood-Glucose rescue from whole PDF text (before urine Âm tính line)
    if "Glucose" not in labs:
        pre_urine = text
        m_u = re.search(r"(?is)\n\s*(?:Nước\s*tiểu|Phân\s*tích\s*nước\s*tiểu)\b", text)
        if m_u:
            pre_urine = text[: m_u.start()]
        got = _find_lab_in_text(
            pre_urine,
            r"(?:\bGlucose\b|Đường\s*(?:huyết|máu)|Duong\s*(?:huyet|mau))",
        )
        if got and re.fullmatch(r"[<>]?\d+(?:[.,]\d+)?", str(got[0])):
            labs["Glucose"] = {"value_raw": got[0], "unit_raw": got[1]}

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
                    # Web label: Urobilinogen (µmol/L), khoảng ~1.69–16.9.
                    # Chỉ đổi khi PDF ghi rõ mg/dL (hoặc Ehrlich).
                    # KHÔNG đoán bừa giá trị 1.0 / <1.5 khi đơn vị đã là µmol/L.
                    if "mg" in u or "ehrlich" in u:
                        num = num * 16.93
                        note = "Urobilinogen mg/dL×16.93→µmol/L"
                    elif "umol" in u or "mmol" in u:
                        note = "Urobilinogen giữ µmol/L (PDF)"
                    elif not u and 0 < num < 1.0:
                        # Không ghi đơn vị, giá trị kiểu 0.2 — hay gặp máy cũ mg/dL
                        num = num * 16.93
                        note = "Urobilinogen 0.x không đơn vị → coi mg/dL×16.93→µmol/L"
                    else:
                        # 1.0 / 3.38 không đơn vị: giữ nguyên số PDF (tránh 1.0→16.93 sai)
                        note = "Urobilinogen giữ số PDF (không đoán đơn vị)"
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
            # Medinet SinhHoaMau_Ure expects mmol/L
            if "mg" in u:
                vnorm, unorm, note = (
                    f"{prefix}{num / 6.0:.2f}",
                    "mmol/L",
                    "mg/dL /6 → mmol/L",
                )
            else:
                vnorm, unorm, note = f"{prefix}{num:g}", unit or "mmol/L", ""

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


def _lab_has_value(labs: dict, key: str) -> bool:
    item = labs.get(key) or {}
    v = item.get("value_web")
    if v in (None, ""):
        v = item.get("value_raw")
    return v not in (None, "")


def classify_pdf_coverage(labs: dict | None) -> str:
    """Classify how complete the PDF lab content is.

    FULL     = has blood core + chemistry core (Urea never required)
    URINE_ONLY = only urine / no blood+chem
    PARTIAL  = some blood or chem but not enough for FULL
    EMPTY    = no usable labs
    """
    labs = labs or {}
    blood_keys = ("WBC", "RBC", "HGB", "PLT")
    chem_keys = ("Glucose", "Creatinine", "AST", "ALT")  # Urea excluded by design
    urine_keys = (
        "Urobilinogen",
        "Glucose_NT",
        "Ketone",
        "Bilirubin_NT",
        "Protein_NT",
        "Nitrite",
        "pH_NT",
        "Mau_NT",
        "Ti_trong",
        "Bach_cau_NT",
    )
    blood_n = sum(1 for k in blood_keys if _lab_has_value(labs, k))
    chem_n = sum(1 for k in chem_keys if _lab_has_value(labs, k))
    urine_n = sum(1 for k in urine_keys if _lab_has_value(labs, k))

    if blood_n == 0 and chem_n == 0 and urine_n == 0:
        return "EMPTY"
    # FULL: đủ công thức máu cốt lõi + sinh hóa cốt lõi (trừ Ure)
    if blood_n >= 3 and chem_n >= 3:
        return "FULL"
    if urine_n > 0 and blood_n == 0 and chem_n == 0:
        return "URINE_ONLY"
    return "PARTIAL"


def extract_pdf(path: Path) -> dict:
    text = read_pdf_text(path)
    header = parse_header(text)
    labs_raw = parse_labs(text)
    labs = normalize_for_web(labs_raw)
    coverage = classify_pdf_coverage(labs)
    sample_kind = classify_sample_kind(header, text)
    return {
        "source_file": str(path),
        "file_name": path.name,
        **header,
        "labs": labs,
        "pdf_coverage": coverage,
        "sample_kind": sample_kind,
        "parse_ok": bool(header.get("ho_ten") and (labs or sample_kind == "OTHER")),
    }
