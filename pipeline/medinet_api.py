#!/usr/bin/env python3
"""Shared Medinet API helpers for Phase B preview/import."""

from __future__ import annotations

import json
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
            val = item.get("value_web")
            if val is None or val == "":
                val = item.get("value_raw")
        else:
            val = item
        if val is None or val == "":
            continue
        if form_key == "NuocTieu_NiTrit":
            nit = map_nitrit(val)
            if nit is not None:
                payload[form_key] = nit
            continue
        if form_key in NUMBER_FIELDS:
            num = _to_number(val)
            if num is not None:
                payload[form_key] = num
            continue
        payload[form_key] = str(val)
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


def insert_cls(token: str, payload: dict, reauth=None) -> tuple[bool, str, dict, str]:
    """Insert/save CLS. Returns (ok, message, raw_result, token).

    Medinet VersionType=3 often returns VersionType-3-Non-Insert-Id even when data is saved.
    Caller should verify with get_cls.
    """
    urlpage = (
        "/app/main/dynamicform/viewer/KSKDK_Phieu_CanLamSang"
        f"?phieukhamId={payload.get('phieukhamId')}"
    )
    q = urllib.parse.urlencode(
        {
            "form_id": CLS_FORM_ID,
            "UrlPage": urlpage,
            "ispopup": "true",
            "istab": "true",
        }
    )
    s, d, token = api(
        token,
        f"/api/services/app/FormViewer/FormToDatabaseInsert?{q}",
        "POST",
        payload,
        reauth=reauth,
    )
    res = (d or {}).get("result") or {}
    ok = bool(res.get("isSucceeded"))
    code = str(res.get("code") or "")
    msg = str(res.get("message") or "")
    # Soft-success: store wrote row but did not return insert id
    if (not ok) and code == "VersionType-3-Non-Insert-Id":
        ok = True
        msg = f"soft-ok:{code}:{msg}"
    return ok, msg or f"http={s}", res, token
