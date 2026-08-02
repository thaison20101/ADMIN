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


def _lab_candidates(item) -> list:
    """Ordered candidates for a lab value (web first, then raw)."""
    if isinstance(item, dict):
        out = []
        for k in ("value_web", "value_raw"):
            if k in item and item.get(k) not in (None, ""):
                out.append(item.get(k))
        # If value_web was explicitly empty but raw has Âm tính / number,
        # still try raw (sanitize will drop illegal (+) positives).
        if not out and item.get("value_raw") not in (None, ""):
            out.append(item.get("value_raw"))
        return out
    if item in (None, ""):
        return []
    return [item]


def labs_to_form_payload(labs: dict, *, phieukham_id: int | str, gioi_tinh: str = "") -> dict:
    """Build formData for Khám định kỳ CLS. Never maps to DHDL_ (Khám tuyển) fields.

    Urine TextBox: PDF 'Âm tính' / 'Am tinh' → exact string 'Negative'.
    Nitrit RadioGroup: int id 5120/5119 (never the string Negative).
    """
    payload = {
        "LoaiKham": LOAI_KHAM_DINH_KY,
        "phieukhamId": int(phieukham_id),
        "IsNamGioi": 1 if str(gioi_tinh).strip().lower() in {"nam", "male", "m", "1"} else 0,
    }
    for lab_key, form_key in LAB_TO_FORM.items():
        item = labs.get(lab_key) or {}
        candidates = _lab_candidates(item)

        if form_key == "NuocTieu_NiTrit":
            nit = None
            for c in candidates:
                nit = map_nitrit(c)
                if nit is not None:
                    break
            if nit is None and isinstance(item, dict):
                nit = map_nitrit(item.get("value_raw"))
            if nit is not None:
                payload[form_key] = int(nit)
            continue

        if form_key in URINE_TEXT_FIELDS:
            cleaned = None
            for c in candidates:
                cleaned = sanitize_urine_text(c)
                if cleaned is not None:
                    break
            # Hard fallback: raw Âm tính even when web was blanked
            if cleaned is None and isinstance(item, dict):
                cleaned = sanitize_urine_text(item.get("value_raw"))
            if cleaned == "Negative" or isinstance(cleaned, (int, float)):
                payload[form_key] = cleaned
            continue

        if not candidates:
            continue
        val = candidates[0]

        if form_key in NUMBER_FIELDS:
            num = _to_number(val)
            if num is None and isinstance(item, dict):
                num = _to_number(item.get("value_raw"))
            if num is not None:
                payload[form_key] = num
            continue

        # unknown non-urine — only send if numeric
        num = _to_number(val)
        if num is not None:
            payload[form_key] = num

    # Absolute scrub: never ship illegal urine text (only number or "Negative")
    for k in list(payload.keys()):
        if k in URINE_TEXT_FIELDS:
            cleaned = sanitize_urine_text(payload[k])
            if cleaned == "Negative" or isinstance(cleaned, (int, float)):
                payload[k] = cleaned
            else:
                del payload[k]
        elif k == "NuocTieu_NiTrit":
            try:
                payload[k] = int(payload[k])
            except Exception:
                del payload[k]
    return payload


def cls_missing_lab_fields(existing: dict | None, payload: dict) -> list[str]:
    """Lab fields present in payload but empty on the web Get/FormViewer row."""
    if not existing:
        return [
            k
            for k in payload
            if (k in NUMBER_FIELDS or k in URINE_TEXT_FIELDS or k == "NuocTieu_NiTrit")
            and k != "SinhHoaMau_Ure"
        ]
    missing = []
    for k, sent in payload.items():
        if k not in NUMBER_FIELDS and k not in URINE_TEXT_FIELDS and k != "NuocTieu_NiTrit":
            continue
        if k == "SinhHoaMau_Ure":
            continue
        got = existing.get(k)
        if got in (None, ""):
            missing.append(k)
            continue
        if k in URINE_TEXT_FIELDS and sent == "Negative":
            gl = re.sub(r"\s+", " ", str(got).strip().lower())
            if gl not in {"negative", "neg"} and not re.search(
                r"âm\s*t[íi]nh|am\s*tinh", gl
            ):
                # web has unexpected non-negative text while we sent Negative
                missing.append(k)
    return missing


def cls_urine_incomplete(existing: dict | None, payload: dict) -> bool:
    """True when payload has urine values that are still empty on web."""
    urine_keys = [k for k in payload if k in URINE_TEXT_FIELDS or k == "NuocTieu_NiTrit"]
    if not urine_keys:
        return False
    miss = cls_missing_lab_fields(existing, {k: payload[k] for k in urine_keys})
    return bool(miss)


def web_cls_looks_incomplete(existing: dict | None, payload: dict | None = None) -> bool:
    """True only when PDF payload fields are missing on web.

    Do not guess from Get alone (Get often omits NuocTieu_Urobilinogen even when
    the form has it). Urea is never required.
    """
    if not existing or not cls_has_lab_values(existing):
        return False
    if not payload:
        return False
    miss = cls_missing_lab_fields(existing, payload)
    return bool(miss)


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


def get_formviewer_cls(token: str, phieukham_id: int | str, reauth=None) -> tuple[dict | None, str]:
    """Web form path — use together with Get for urine field presence."""
    s, d, token = api(
        token,
        f"/api/services/app/FormViewer/FormViewerData?form_id={CLS_FORM_ID}"
        f"&SessionSiteId={SITE_ID}&UrlPage=",
        "POST",
        to_fparams({"phieukhamId": phieukham_id}),
        reauth=reauth,
    )
    fd = (((d or {}).get("result") or {}).get("data") or {}).get("formData") or []
    return (fd[0] if fd else None), token


def merge_cls_rows(*rows: dict | None) -> dict:
    out: dict = {}
    for row in rows:
        if not row:
            continue
        for k, v in row.items():
            if v in (None, ""):
                continue
            if out.get(k) in (None, ""):
                out[k] = v
    # Keep empty keys from first row for markers
    if rows and rows[0]:
        for k, v in rows[0].items():
            out.setdefault(k, v)
    return out


def load_cls_view(token: str, phieukham_id: int | str, reauth=None) -> tuple[dict | None, str]:
    """Merged Get + FormViewer row (best view of what the UI has)."""
    row_g, token = get_cls(token, phieukham_id, reauth=reauth)
    row_f, token = get_formviewer_cls(token, phieukham_id, reauth=reauth)
    if not row_g and not row_f:
        return None, token
    return merge_cls_rows(row_g, row_f), token


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


def _is_urine_format_error(msg: str) -> bool:
    m = (msg or "").lower()
    return (
        "negative" in m
        or "định dạng" in m
        or "dinh dang" in m
        or "nuoctieu" in m
        or "nước tiểu" in m
        or "nuoc tieu" in m
    )


def _uro_value_variants(val) -> list:
    """Medinet often rejects float urobilinogen; try comma/string forms."""
    out = []
    if val is None or val == "":
        return out
    if val == "Negative":
        return ["Negative"]
    try:
        num = float(str(val).replace(",", "."))
    except Exception:
        return [str(val)]
    # Prefer Vietnamese decimal comma (web placeholder uses dấu phẩy)
    out.append(str(round(num, 2)).replace(".", ","))
    out.append(f"{round(num, 2):g}".replace(".", ","))
    out.append(str(round(num, 2)))
    out.append(round(num, 2))
    out.append(num)
    # dedupe preserve order
    seen = set()
    uniq = []
    for v in out:
        key = (type(v).__name__, str(v))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(v)
    return uniq


def insert_cls(token: str, payload: dict, reauth=None) -> tuple[bool, str, dict, str]:
    """Save CLS via store Set (reliable). Returns (ok, message, raw_result, token).

    Prefer KSKDK_Phieu_CanLamSang_Set with phieukhamId.

    On urine-format errors: keep blood + Nitrit, and retry urine TextBox fields
    one-by-one so Âm tính→Negative values are still saved. Never treat
    "strip all urine" as a full success (that left web missing nước tiểu).
    """
    if "phieukhamId" not in payload:
        return False, "missing phieukhamId", {}, token

    # Ensure urine text is only number or exact "Negative" before first Set
    clean = dict(payload)
    wanted_uro = None
    for k in list(clean.keys()):
        if k in URINE_TEXT_FIELDS:
            cleaned = sanitize_urine_text(clean[k])
            if cleaned == "Negative" or isinstance(cleaned, (int, float)):
                if k == "NuocTieu_Urobilinogen" and isinstance(cleaned, (int, float)):
                    wanted_uro = cleaned
                    # First attempt: comma decimal string (web VN format)
                    clean[k] = str(round(float(cleaned), 2)).replace(".", ",")
                else:
                    clean[k] = cleaned
            else:
                del clean[k]
        elif k == "NuocTieu_NiTrit":
            try:
                clean[k] = int(clean[k])
            except Exception:
                del clean[k]

    ok, msg, res, token = _set_cls(token, clean, reauth=reauth)
    if ok:
        return True, msg or "SET ok", res, token

    if not _is_urine_format_error(msg):
        return False, f"SET:{msg}", res, token

    # Base: blood + chemistry + Nitrit (no urine text)
    base = {k: v for k, v in clean.items() if k not in URINE_TEXT_FIELDS}
    if "NuocTieu_NiTrit" in clean:
        try:
            base["NuocTieu_NiTrit"] = int(clean["NuocTieu_NiTrit"])
        except Exception:
            base.pop("NuocTieu_NiTrit", None)

    urine_items = [(k, clean[k]) for k in URINE_TEXT_FIELDS if k in clean]
    kept_urine: dict = {}
    last_msg = msg
    last_res = res

    # Prefer Negative fields first (most common PDF value), then numbers
    urine_items.sort(key=lambda kv: (0 if kv[1] == "Negative" else 1, kv[0]))

    for uk, uv in urine_items:
        if uk == "NuocTieu_Urobilinogen":
            variants = _uro_value_variants(wanted_uro if wanted_uro is not None else uv)
        else:
            variants = [uv]
        accepted = None
        for variant in variants:
            trial = dict(base)
            trial.update(kept_urine)
            trial[uk] = variant
            ok_t, msg_t, res_t, token = _set_cls(token, trial, reauth=reauth)
            last_msg, last_res = msg_t, res_t
            if ok_t:
                accepted = variant
                break
        if accepted is not None:
            kept_urine[uk] = accepted

    # If urobilinogen still missing, try Set with ONLY id + uro (minimal payload)
    if wanted_uro is not None and "NuocTieu_Urobilinogen" not in kept_urine:
        for variant in _uro_value_variants(wanted_uro):
            solo = {
                "LoaiKham": base.get("LoaiKham", LOAI_KHAM_DINH_KY),
                "phieukhamId": base["phieukhamId"],
                "NuocTieu_Urobilinogen": variant,
            }
            if "IsNamGioi" in base:
                solo["IsNamGioi"] = base["IsNamGioi"]
            if "cdId" in base:
                solo["cdId"] = base["cdId"]
            # Keep other accepted urine too if any
            solo.update(kept_urine)
            ok_u, msg_u, res_u, token = _set_cls(token, solo, reauth=reauth)
            last_msg, last_res = msg_u, res_u
            if ok_u:
                kept_urine["NuocTieu_Urobilinogen"] = variant
                break

    if kept_urine:
        final = dict(base)
        final.update(kept_urine)
        ok_f, msg_f, res_f, token = _set_cls(token, final, reauth=reauth)
        dropped = [k for k, _ in urine_items if k not in kept_urine]
        if wanted_uro is not None and "NuocTieu_Urobilinogen" not in kept_urine:
            dropped = list(set(dropped + ["NuocTieu_Urobilinogen"]))
        note = f"SET-urine-partial:kept={len(kept_urine)}"
        if dropped:
            note += f";dropped={','.join(dropped)}"
        if ok_f:
            # If PDF had urobilinogen but it was dropped, mark NOT full success
            if wanted_uro is not None and "NuocTieu_Urobilinogen" not in kept_urine:
                return False, f"{note}:URO_DROPPED:{msg_f}", res_f, token
            return True, f"{note}:{msg_f}", res_f, token
        if wanted_uro is not None and "NuocTieu_Urobilinogen" not in kept_urine:
            return False, f"SET-urine-partial-base:URO_DROPPED:{last_msg}", last_res, token
        return True, f"SET-urine-partial-base:{last_msg}", last_res, token

    # Could not keep any urine text — save blood only, but FAIL so repair re-runs
    ok2, msg2, res2, token = _set_cls(token, base, reauth=reauth)
    if ok2:
        return (
            False,
            f"SET-urine-all-dropped:{msg}; blood_saved:{msg2}",
            {"set": res, "blood": res2},
            token,
        )
    return False, f"SET:{msg}; SET-retry:{msg2}", {"set": res, "retry": res2}, token
