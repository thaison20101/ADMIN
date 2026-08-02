#!/usr/bin/env python3
"""Shared Medinet API helpers for Phase B preview/import."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BE = "https://be-qlskcd.medinet.org.vn"
SITE_ID = "130"
CLS_FORM_ID = 1000250
CLS_DATASOURCE_ID = 97
CLS_STORE_GET = "KSKDK_Phieu_CanLamSang_Get"
CLS_STORE_SET = "KSKDK_Phieu_CanLamSang_Set"
LOAI_KHAM_DINH_KY = 5152
LOAI_KHAM_TUYEN = 5153
NITRIT_AM_TINH = 5120
NITRIT_DUONG_TINH = 5119


def authenticate(user: str, password: str) -> str:
    req = urllib.request.Request(
        f"{BE}/api/TokenAuth/Authenticate",
        data=json.dumps(
            {"userNameOrEmailAddress": user, "password": password, "rememberClient": True}
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read())
    if not body.get("success"):
        raise RuntimeError(f"Auth failed: {body}")
    return body["result"]["accessToken"]


def to_fparams(obj: dict) -> list:
    return [{"Varible": k, "Value": "" if v is None else str(v)} for k, v in obj.items()]


def api(token: str, path: str, method: str = "GET", body=None, reauth=None):
    """Call Medinet API. Optional reauth() refreshes token on 401."""
    url = f"{BE}{path}" if path.startswith("/") else path
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    last = None
    for attempt in range(5):
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "SessionSiteId": SITE_ID,
        }
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, json.loads(r.read()), token
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"error": raw[:800]}
            if (e.code == 401 or parsed.get("unAuthorizedRequest")) and reauth and attempt < 4:
                token = reauth()
                time.sleep(0.4)
                continue
            return e.code, parsed, token
        except Exception as e:
            last = e
            time.sleep(0.8 + attempt)
            if reauth and attempt < 4:
                try:
                    token = reauth()
                except Exception:
                    pass
    return 0, {"error": str(last)}, token


# PDF/Excel lab key → Medinet định kỳ form field (never DHDL_/Khám tuyển)
LAB_TO_FORM = {
    "RBC": "CongThucMau_SLHC",
    "HGB": "XNM_HuyetSacTo",
    "HCT": "XNM_Hematocrit",
    "MCV": "XNM_MCV",
    "MCH": "XNM_MCH",
    "MCHC": "XNM_MCHC",
    "RDW": "XNM_RDW",
    "WBC": "CongThucMau_SLBC",
    "Neutrophils_count": "SLBC_TrungTinh",
    "Lymphocytes_count": "SLBC_lympho",
    "Monocytes_count": "SLBC_DonNhan",
    "Eosinophils_count": "SLBC_AiToan",
    "Basophils_count": "SLBC_AiKiem",
    "PLT": "CongThucMau_SLTC",
    "Glucose": "SinhHoaMau_DuongMau",
    "Urea": "SinhHoaMau_Ure",
    "Creatinine": "SinhHoaMau_Creatinin",
    "AST": "SinhHoaMau_ASAT_GOT",
    "ALT": "SinhHoaMau_ALAT_GPT",
    "Ti_trong": "NuocTieu_TiTrong",
    "pH_NT": "NuocTieu_pH",
    "Bach_cau_NT": "NuocTieu_BC",
    "Mau_NT": "NuocTieu_HC",
    "Nitrite": "NuocTieu_NiTrit",
    "Protein_NT": "NuocTieu_Protein",
    "Glucose_NT": "NuocTieu_Duong",
    "Ketone": "NuocTieu_Cetonic",
    "Bilirubin_NT": "NuocTieu_Bilirubin",
    "Urobilinogen": "NuocTieu_Urobilinogen",
}

NUMBER_FIELDS = {
    "CongThucMau_SLHC",
    "XNM_HuyetSacTo",
    "XNM_Hematocrit",
    "XNM_MCV",
    "XNM_MCH",
    "XNM_MCHC",
    "XNM_RDW",
    "CongThucMau_SLBC",
    "SLBC_TrungTinh",
    "SLBC_lympho",
    "SLBC_DonNhan",
    "SLBC_AiToan",
    "SLBC_AiKiem",
    "CongThucMau_SLTC",
    "SinhHoaMau_DuongMau",
    "SinhHoaMau_Ure",
    "SinhHoaMau_Creatinin",
    "SinhHoaMau_ASAT_GOT",
    "SinhHoaMau_ALAT_GPT",
}


def _to_number(val):
    if val is None or val == "":
        return None
    s = str(val).strip().replace(",", ".")
    if s[:1] in "<>":
        s = s[1:]
    try:
        f = float(s)
        return int(f) if f.is_integer() else f
    except Exception:
        return None


def map_nitrit(val) -> int | None:
    if val is None or val == "":
        return None
    s = str(val).strip().lower()
    if s in {"5120", "5119"}:
        return int(s)
    if "âm" in s or "am tinh" in s or s in {"negative", "neg", "-"}:
        return NITRIT_AM_TINH
    if "duong" in s or "dương" in s or s in {"positive", "pos", "+", "( + )", "(+)"}:
        return NITRIT_DUONG_TINH
    return None


# Medinet urine TextBox fields: only number or exact "Negative"
URINE_TEXT_FIELDS = {
    "NuocTieu_TiTrong",
    "NuocTieu_pH",
    "NuocTieu_BC",
    "NuocTieu_HC",
    "NuocTieu_Protein",
    "NuocTieu_Duong",
    "NuocTieu_Cetonic",
    "NuocTieu_Bilirubin",
    "NuocTieu_Urobilinogen",
    "NuocTieu_Khac",
}


def sanitize_urine_text(val) -> str | float | None:
    """Return value allowed by Medinet urine TextBox, else None (skip field).

    Medinet rejects anything except a number or the exact string Negative
    (e.g. Âm tính, Neg, ( + ) all fail).
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    # normalize unicode / whitespace
    s = re.sub(r"\s+", " ", s)
    sl = s.lower()
    # negative variants → exact Negative
    if re.search(r"âm\s*t[íi]nh|am\s*tinh", sl) or sl in {
        "negative",
        "neg",
        "-",
        "âm",
        "am",
    }:
        return "Negative"
    # qualitative positive without concentration → skip
    if re.search(r"\(\s*\+\s*\)", s) or re.search(r"d[uư][ơo]ng\s*t[íi]nh|positive|^pos$|^\+$", sl):
        return None
    # bare number (optionally with <> )
    num = _to_number(s)
    if num is not None:
        return num
    # number stuck with unit e.g. "1.020 " / "6 pH" — take leading number only
    m = re.match(r"^[<>]?\s*(\d+(?:[.,]\d+)?)", s)
    if m:
        num = _to_number(m.group(1))
        if num is not None:
            return num
    return None


def labs_to_form_payload(labs: dict, *, phieukham_id: int | str, gioi_tinh: str = "") -> dict:
    """Build formData for Khám định kỳ CLS. Never maps to DHDL_ (Khám tuyển) fields."""
    payload = {
        "LoaiKham": LOAI_KHAM_DINH_KY,
        "phieukhamId": int(phieukham_id),
        "IsNamGioi": 1 if str(gioi_tinh).strip().lower() in {"nam", "male", "m", "1"} else 0,
    }
    for lab_key, form_key in LAB_TO_FORM.items():
        item = labs.get(lab_key) or {}
        if isinstance(item, dict):
            # Prefer value_web when present (even if ""). Do NOT fall back to
            # value_raw for urine — empty web means "skip", raw may be Âm tính/(+).
            if "value_web" in item:
                val = item.get("value_web")
                if (val is None or val == "") and form_key not in URINE_TEXT_FIELDS and form_key != "NuocTieu_NiTrit":
                    val = item.get("value_raw")
            else:
                val = item.get("value_raw")
        else:
            val = item
        if val is None or val == "":
            continue
        if form_key == "NuocTieu_NiTrit":
            # Set-store needs int id; "Negative" string fails convert-to-int
            nit = map_nitrit(val)
            if nit is None and isinstance(item, dict):
                nit = map_nitrit(item.get("value_raw"))
            if nit is not None:
                payload[form_key] = int(nit)
            continue
        if form_key in NUMBER_FIELDS:
            num = _to_number(val)
            if num is not None:
                payload[form_key] = num
            continue
        if form_key in URINE_TEXT_FIELDS:
            cleaned = sanitize_urine_text(val)
            if cleaned is None and isinstance(item, dict):
                # last chance: raw if web was weird, still sanitized
                cleaned = sanitize_urine_text(item.get("value_raw"))
            if cleaned is not None:
                # final hard gate
                if cleaned == "Negative" or isinstance(cleaned, (int, float)):
                    payload[form_key] = cleaned
            continue
        # unknown non-urine — only send if numeric
        num = _to_number(val)
        if num is not None:
            payload[form_key] = num

    # Absolute scrub: never ship illegal urine text
    for k in list(payload.keys()):
        if k in URINE_TEXT_FIELDS:
            cleaned = sanitize_urine_text(payload[k])
            if cleaned is None:
                del payload[k]
            else:
                payload[k] = cleaned
        elif k == "NuocTieu_NiTrit":
            try:
                payload[k] = int(payload[k])
            except Exception:
                del payload[k]
    return payload


def get_cls(token: str, phieukham_id: int | str, reauth=None) -> tuple[dict | None, str]:
    s, d, token = api(
        token,
        f"/api/services/app/DRViewer/ExecuteStoreWithParam_ByDatasource"
        f"?dataSourceId={CLS_DATASOURCE_ID}&store={CLS_STORE_GET}",
        "POST",
        to_fparams({"phieukhamId": phieukham_id}),
        reauth=reauth,
    )
    rows = ((d or {}).get("result") or {}).get("data") or []
    return (rows[0] if rows else None), token


def cls_has_lab_values(row: dict | None) -> bool:
    if not row:
        return False
    markers = (
        "CongThucMau_SLBC",
        "CongThucMau_SLHC",
        "XNM_HuyetSacTo",
        "DHDL_CongThucMau_SLBC",
        "DHDL_XNM_HuyetSacTo",
    )
    return any(row.get(k) not in (None, "") for k in markers)


def verify_cls_saved(
    token: str,
    phieukham_id: int | str,
    payload: dict | None = None,
    reauth=None,
) -> tuple[bool, str, str]:
    """Confirm CLS is readable on the same phieukhamId the UI uses.

    Returns (ok, detail, token).
    """
    row, token = get_cls(token, phieukham_id, reauth=reauth)
    if not cls_has_lab_values(row):
        return False, "Get(phieukhamId) empty", token

    # Spot-check a value we sent (avoid false IMPORTED on wrong id)
    if payload:
        for key in ("CongThucMau_SLBC", "XNM_HuyetSacTo", "CongThucMau_SLHC"):
            if key in payload and payload[key] not in (None, ""):
                got = row.get(key)
                if got in (None, ""):
                    return False, f"missing {key} after save", token
                try:
                    if abs(float(got) - float(payload[key])) > 0.001:
                        return False, f"mismatch {key}: sent={payload[key]} got={got}", token
                except Exception:
                    if str(got) != str(payload[key]):
                        return False, f"mismatch {key}: sent={payload[key]} got={got}", token
                break

    # Also confirm FormViewer path (same as web form)
    s, d, token = api(
        token,
        f"/api/services/app/FormViewer/FormViewerData?form_id={CLS_FORM_ID}"
        f"&SessionSiteId={SITE_ID}&UrlPage=",
        "POST",
        to_fparams({"phieukhamId": phieukham_id}),
        reauth=reauth,
    )
    fd = (((d or {}).get("result") or {}).get("data") or {}).get("formData") or []
    if not fd or not cls_has_lab_values(fd[0]):
        return False, "FormViewerData empty after save", token
    return True, "verified Get+FormViewer", token


def _set_cls(token: str, payload: dict, reauth=None):
    s, d, token = api(
        token,
        f"/api/services/app/DRViewer/ExecuteStoreWithParam_ByDatasource"
        f"?dataSourceId={CLS_DATASOURCE_ID}&store={CLS_STORE_SET}",
        "POST",
        to_fparams(payload),
        reauth=reauth,
    )
    res = (d or {}).get("result") or {}
    ok = bool(res.get("isSucceeded"))
    msg = str(res.get("message") or "")
    data = res.get("data")
    if ok and isinstance(data, list) and data:
        err = data[0].get("ErrorMessage") if isinstance(data[0], dict) else None
        if err:
            ok = False
            msg = str(err)
    return ok, msg or f"http={s}", res, token


def insert_cls(token: str, payload: dict, reauth=None) -> tuple[bool, str, dict, str]:
    """Save CLS via store Set (reliable). Returns (ok, message, raw_result, token).

    Prefer KSKDK_Phieu_CanLamSang_Set with phieukhamId. On urine-format errors,
    retry once with urine text fields stripped (keep blood + Nitrit id).
    """
    if "phieukhamId" not in payload:
        return False, "missing phieukhamId", {}, token

    ok, msg, res, token = _set_cls(token, payload, reauth=reauth)
    if ok:
        return True, msg or "SET ok", res, token

    # Retry without risky urine text fields if format error
    if "Negative" in msg or "định dạng" in msg.lower() or "dinh dang" in msg.lower():
        trimmed = {
            k: v
            for k, v in payload.items()
            if k not in URINE_TEXT_FIELDS
        }
        # keep Nitrit only if int
        if "NuocTieu_NiTrit" in payload:
            try:
                trimmed["NuocTieu_NiTrit"] = int(payload["NuocTieu_NiTrit"])
            except Exception:
                pass
        ok2, msg2, res2, token = _set_cls(token, trimmed, reauth=reauth)
        if ok2:
            return True, f"SET-no-urine-text:{msg2}", res2, token
        return False, f"SET:{msg}; SET-retry:{msg2}", {"set": res, "retry": res2}, token

    return False, f"SET:{msg}", res, token
