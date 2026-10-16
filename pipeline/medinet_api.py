#!/usr/bin/env python3
"""Shared Medinet API helpers for Phase B preview/import."""

from __future__ import annotations

import json
import re
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

from medinet_ssl import (
    install_medinet_https_opener,
    medinet_http_headers,
    urlopen as _urlopen,
)

# May A: install unverified HTTPS opener before any Medinet call
install_medinet_https_opener()

BE = "https://be-qlskcd.medinet.org.vn"
SITE_ID = "130"
CLS_FORM_ID = 1000250
CLS_DATASOURCE_ID = 97
CLS_STORE_GET = "KSKDK_Phieu_CanLamSang_Get"
CLS_STORE_SET = "KSKDK_Phieu_CanLamSang_Set"
CLS_MAUKHAM = "mauphieudk"
LOAI_KHAM_DINH_KY = 5152
LOAI_KHAM_TUYEN = 5153
NITRIT_AM_TINH = 5120
NITRIT_DUONG_TINH = 5119


def _cls_formviewer_urlpage(record_id: int | str, *, maukham: str = CLS_MAUKHAM) -> str:
    """Same UrlPage the browser uses for Khám cận lâm sàng (Lưu thay đổi)."""
    return (
        "/nav_group/kskdk_thongtinkham/app/main/dynamicform/viewer/"
        f"KSKDK_Phieu_CanLamSang?TTHCId={record_id}&maukham={maukham}"
    )


def _auth_fail_detail(body: dict | None, raw: str = "") -> str:
    if isinstance(body, dict):
        err = body.get("error") or {}
        if isinstance(err, dict):
            detail = err.get("details") or err.get("message") or ""
            if detail:
                return str(detail)
        return json.dumps(body, ensure_ascii=False)[:400]
    return (raw or "")[:400]


def authenticate(user: str, password: str, *, timeout: float = 60, retries: int = 3) -> str:
    """Login Medinet. Retries on timeout/network; raises RuntimeError on bad password.

    Must send browser User-Agent: Medinet WAF drops bare Python-urllib (read timeout
    forever) while Chrome / Mozilla UA returns in ~2s.

    Note: Medinet returns HTTP 500 + JSON {success:false, Invalid user name or password}
    for wrong credentials (not HTTP 401).
    """
    last_err: Exception | None = None
    payload = json.dumps(
        {"userNameOrEmailAddress": user, "password": password, "rememberClient": True}
    ).encode()
    headers = medinet_http_headers({"Content-Type": "application/json"})
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(
                f"{BE}/api/TokenAuth/Authenticate",
                data=payload,
                headers=headers,
                method="POST",
            )
            with _urlopen(req, timeout=timeout) as r:
                body = json.loads(r.read())
            if not body.get("success"):
                detail = _auth_fail_detail(body)
                raise RuntimeError(
                    f"Auth failed (sai user/pass hoac bi khoa) user={user}: {detail}"
                )
            return body["result"]["accessToken"]
        except RuntimeError:
            raise
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            body = None
            try:
                body = json.loads(raw)
            except Exception:
                pass
            detail = _auth_fail_detail(body, raw).lower()
            # Wrong password often comes as HTTP 500 + "Invalid user name or password"
            if (
                e.code in (400, 401, 403, 500)
                and body is not None
                and (
                    body.get("success") is False
                    or "invalid user" in detail
                    or "password" in detail
                    or "login failed" in detail
                )
            ):
                raise RuntimeError(
                    f"Auth failed (sai user/pass) user={user} http={e.code}: "
                    f"{_auth_fail_detail(body, raw)}"
                ) from e
            last_err = e
            msg = f"http {e.code} {detail}"
            transient = e.code >= 500 or e.code == 429
            if not transient or attempt >= retries - 1:
                break
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            transient = any(
                x in msg
                for x in (
                    "timed out",
                    "timeout",
                    "temporarily unavailable",
                    "connection reset",
                    "connection aborted",
                    "name or service not known",
                    "getaddrinfo",
                    "10060",
                    "10054",
                    "10061",
                )
            )
            if not transient or attempt >= retries - 1:
                break
            time.sleep(1.5 * (attempt + 1))
    raise TimeoutError(
        f"Auth TIMEOUT toi {BE} (user={user}). "
        f"Pass co the DUNG - mang/proxy/DNS toi Medinet bi treo. last={last_err}"
    )


def login_accounts(
    accounts: list[dict],
    *,
    require_first: bool = True,
) -> tuple[list[dict], dict[str, str]]:
    """Authenticate accounts; drop secondary failures (TK2 stale pass).

    Returns (working_accounts, tokens). If require_first and TK1 fails, raises.
    """
    working: list[dict] = []
    tokens: dict[str, str] = {}
    for i, acct in enumerate(accounts):
        try:
            tok = authenticate(acct["user"], acct["password"])
            working.append(acct)
            tokens[acct["id"]] = tok
            print(f"AUTH_OK {acct['user']} token_len={len(tok or '')}", flush=True)
        except Exception as e:
            if i == 0 and require_first:
                raise
            print(f"AUTH_WARN skip {acct['user']}: {e}", flush=True)
            print(
                "AUTH_WARN: tiep tuc voi TK da login OK (can pass TK2 moi neu can dien TK2).",
                flush=True,
            )
    if not working:
        raise RuntimeError("Khong login duoc TK Medinet nao")
    return working, tokens


def _api_error_message(body) -> str:
    if not isinstance(body, dict):
        return ""
    res = body.get("result")
    if isinstance(res, dict):
        msg = str(res.get("message") or "")
        if msg:
            return msg
    err = body.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("details") or "")
    if err:
        return str(err)
    return ""


def _is_access_denied(status: int | None, body=None, msg: str = "") -> bool:
    if status == 403:
        return True
    text = (msg or _api_error_message(body) or "").lower()
    return "access denied" in text or "không có quyền" in text or "khong co quyen" in text


def probe_drviewer_access(token: str) -> tuple[bool, str]:
    """Return (ok, detail). TK1 may auth but lack DRViewer ExecuteStore (403).

    Without this permission index/live rematch fail. CLS can still use FormViewer.
    """
    path = (
        f"/api/services/app/DRViewer/ExecuteStoreWithParam_ByDatasource"
        f"?dataSourceId={CLS_DATASOURCE_ID}&store={CLS_STORE_GET}"
    )
    status, body, _tok = api(token, path, "POST", to_fparams({"phieukhamId": 1}))
    msg = _api_error_message(body)
    if _is_access_denied(status, body, msg):
        return False, f"http={status} {msg or 'Access denied DRViewer'}"
    # 200 with empty CLS for pid=1 is fine — permission exists
    if status in (200, 404) or (isinstance(body, dict) and body.get("success") is True):
        return True, f"http={status} ok"
    return True, f"http={status} {msg or 'ok'}"


def probe_formviewer_cls(token: str) -> tuple[bool, str]:
    """Return (ok, detail). FormViewerData is the light CLS read/write path."""
    path = (
        f"/api/services/app/FormViewer/FormViewerData?form_id={CLS_FORM_ID}"
        f"&SessionSiteId={SITE_ID}&UrlPage="
    )
    status, body, _tok = api(
        token,
        path,
        "POST",
        to_fparams({"phieukhamId": 1}),
        extra_headers={"displaymode": "0"},
    )
    msg = _api_error_message(body)
    if _is_access_denied(status, body, msg):
        return False, f"http={status} {msg or 'Access denied FormViewer'}"
    if status == 200 or (isinstance(body, dict) and body.get("success") is True):
        return True, f"http={status} ok"
    if status in (404,):
        # Form exists but empty pid — still reachable
        return True, f"http={status} reachable"
    return False, f"http={status} {msg or 'FormViewer fail'}"


# Report codes for PostDataWithDataOutput live patient lookup (not ExecuteStore).
POSTDATA_REPORTS = [
    ("M3", "KSKDK_DanhSach_KSK_M13", "NgayTao"),
    ("M2", "KSKDK_DanhSach_KSK_M12", "KSKDK_NgayKham"),
    ("M4", "KSKDK_DanhSach_KSK_NguoiCaoTuoi_Report", "KSKDK_NgayKham"),
    ("M11", "KSKDK_DanhSach_KSK_M11", "KSKDK_NgayKham"),
]


def _get_report_meta(token: str, code: str, reauth=None) -> dict | None:
    s, d, _tok = api(
        token,
        f"/api/services/app/DRReport/GetIdByCode?Code={code}&SessionSiteId={SITE_ID}",
        reauth=reauth,
    )
    items = ((d or {}).get("result") or {}).get("data") or []
    return items[0] if items else None


def postdata_fetch_page(
    token: str,
    report_id: int | str,
    code: str,
    filters: dict,
    *,
    page: int = 1,
    page_size: int = 100,
    reauth=None,
) -> tuple[list, int, str]:
    """POST DRViewer/PostDataWithDataOutput — live list/filter by name/CCCD.

    Different method from ExecuteStore; may work when ExecuteStore is 403.
    Returns (rows, http_status, token).
    """
    url_page = (
        f"/app/main/dynamicreport/report/viewer-utility/{code}"
    )
    q = urllib.parse.urlencode(
        {
            "id": str(report_id),
            "SessionSiteId": SITE_ID,
            "UrlPage": url_page,
            "ispopup": "false",
            "istab": "false",
        }
    )
    params = [{"Varible": k, "Value": v} for k, v in filters.items()]
    params += [
        {"Varible": "ReportId", "Value": report_id},
        {"Varible": "PageSize", "Value": page_size},
        {"Varible": "PageNumber", "Value": page},
        {"Varible": "PageDefaultFilter", "Value": None},
    ]
    s, d, token = api(
        token,
        f"/api/services/app/DRViewer/PostDataWithDataOutput?{q}",
        "POST",
        params,
        reauth=reauth,
        extra_headers={"displaymode": "0"},
    )
    if _is_access_denied(s, d):
        return [], s, token
    rows = ((d or {}).get("result") or {}).get("data")
    if not isinstance(rows, list):
        rows = []
    return rows, s, token


def probe_postdata_access(token: str) -> tuple[bool, str]:
    """Return (ok, detail) for PostDataWithDataOutput (M3 one page)."""
    meta = _get_report_meta(token, "KSKDK_DanhSach_KSK_M13")
    if not meta:
        return False, "GetIdByCode M3 missing"
    rid = meta.get("id") or meta.get("Id") or 1002176
    code = "KSKDK_DanhSach_KSK_M13"
    rows, status, _tok = postdata_fetch_page(
        token,
        rid,
        code,
        {
            "KSKDK_HoVaTen": None,
            "KSKDK_DinhDanhCaNhan": None,
            "NgayTao": "01/01/2026 - 31/12/2026",
        },
        page=1,
        page_size=5,
    )
    if _is_access_denied(status, None) or status == 403:
        return False, f"http={status} Access denied PostData"
    if status == 200:
        return True, f"http={status} rows={len(rows)}"
    return False, f"http={status} PostData fail"


def lookup_tthc_by_name_cccd(
    token: str,
    *,
    name: str = "",
    cccd: str = "",
    year: str = "",
    date_from: str = "01/07/2026",
    date_to: str = "",
    reauth=None,
) -> tuple[dict | None, str, str]:
    """Find one TTHC via PostData filters (name and/or CCCD). Returns (rec, detail, token).

    Prefer unique CCCD hit; else unique folded name+year across M2/M3/M4/M11.
    """
    from datetime import date as _date
    from datetime import timedelta

    if not date_to:
        date_to = _date.today().strftime("%d/%m/%Y")
    try:
        d0 = _date(int(date_from.split("/")[2]), int(date_from.split("/")[1]), int(date_from.split("/")[0]))
        d0 = d0 - timedelta(days=60)
        date_from_w = d0.strftime("%d/%m/%Y")
    except Exception:
        date_from_w = date_from
    dr = f"{date_from_w} - {date_to}"
    name = (name or "").strip()
    cccd = re.sub(r"\D", "", str(cccd or ""))
    if len(cccd) < 9:
        cccd = ""
    if not name and not cccd:
        return None, "no_name_or_cccd", token

    def _fold(s: str) -> str:
        import unicodedata

        s2 = unicodedata.normalize("NFD", (s or "").upper())
        s2 = "".join(c for c in s2 if unicodedata.category(c) != "Mn")
        return re.sub(r"\s+", " ", s2).strip()

    fold_want = _fold(name)
    hits: list[dict] = []
    last_detail = "no_hits"

    for mau, code, date_field in POSTDATA_REPORTS:
        meta = _get_report_meta(token, code, reauth=reauth)
        if not meta:
            continue
        rid = meta.get("id") or meta.get("Id")
        if not rid:
            continue
        # Prefer CCCD-only filter when available (unique)
        filter_sets = []
        if cccd:
            filter_sets.append(
                {
                    "KSKDK_HoVaTen": None,
                    "KSKDK_DinhDanhCaNhan": cccd,
                    date_field: dr,
                    "NgayTao": dr,
                    "KSKDK_NgayKham": dr,
                }
            )
        if name:
            filter_sets.append(
                {
                    "KSKDK_HoVaTen": name,
                    "KSKDK_DinhDanhCaNhan": None,
                    date_field: dr,
                    "NgayTao": dr,
                    "KSKDK_NgayKham": dr,
                }
            )
        for filters in filter_sets:
            rows, status, token = postdata_fetch_page(
                token, rid, code, filters, page=1, page_size=50, reauth=reauth
            )
            if status == 403 or _is_access_denied(status, None):
                return None, f"postdata_denied http={status}", token
            for r in rows:
                if not isinstance(r, dict):
                    continue
                r = {**r, "_mau": mau, "_via": "postdata"}
                if cccd:
                    raw_cc = ""
                    for k in (
                        "SoDinhDanh",
                        "CCCD",
                        "CMND",
                        "KSKDK_DinhDanhCaNhan",
                        "SoCMND",
                    ):
                        raw_cc = re.sub(r"\D", "", str(r.get(k) or ""))
                        if len(raw_cc) >= 9:
                            break
                    if raw_cc and raw_cc == cccd:
                        hits.append(r)
                        continue
                if fold_want:
                    hn = _fold(str(r.get("HoTen") or r.get("KSKDK_HoVaTen") or ""))
                    if hn != fold_want:
                        continue
                    if year:
                        ys = str(r.get("NgaySinh") or "")
                        y = ""
                        m = re.search(r"(19|20)\d{2}", ys)
                        if m:
                            y = m.group(0)
                        if y and y != str(year):
                            continue
                    hits.append(r)
            if hits:
                break
        if hits:
            break

    if not hits:
        return None, last_detail or "no_hits", token

    # Dedupe by pid
    seen = set()
    uniq = []
    for h in hits:
        pid = h.get("phieukhamId") or h.get("Id")
        if pid in seen:
            continue
        seen.add(pid)
        uniq.append(h)
    if len(uniq) == 1:
        rec = uniq[0]
        pid = rec.get("phieukhamId") or rec.get("Id")
        if pid is not None and "phieukhamId" not in rec:
            rec["phieukhamId"] = pid
        return rec, f"postdata_unique mau={rec.get('_mau')}", token
    # Multiple: prefer CCCD exact already filtered; else refuse ambiguous
    if cccd and len(uniq) > 1:
        return None, f"postdata_ambiguous_cccd n={len(uniq)}", token
    if fold_want and year:
        # already year-filtered; still ambiguous
        return None, f"postdata_ambiguous_name n={len(uniq)}", token
    return None, f"postdata_ambiguous n={len(uniq)}", token


def probe_fill_capabilities(tokens: dict[str, str]) -> dict:
    """Probe ExecuteStore + PostData + FormViewer. Soft gate for fill vs rematch."""
    caps = {
        "drviewer_ok": False,
        "postdata_ok": False,
        "formviewer_ok": False,
        "drviewer_detail": "",
        "postdata_detail": "",
        "formviewer_detail": "",
        "accounts": {},
    }
    for aid, tok in tokens.items():
        d_ok, d_det = probe_drviewer_access(tok)
        p_ok, p_det = probe_postdata_access(tok)
        f_ok, f_det = probe_formviewer_cls(tok)
        print(
            f"probe: {aid} ExecuteStore={'OK' if d_ok else 'DENIED'} {d_det} | "
            f"PostData={'OK' if p_ok else 'DENIED'} {p_det} | "
            f"FormViewer={'OK' if f_ok else 'DENIED'} {f_det}",
            flush=True,
        )
        caps["accounts"][aid] = {
            "drviewer_ok": d_ok,
            "postdata_ok": p_ok,
            "formviewer_ok": f_ok,
            "drviewer_detail": d_det,
            "postdata_detail": p_det,
            "formviewer_detail": f_det,
        }
        if d_ok:
            caps["drviewer_ok"] = True
            caps["drviewer_detail"] = d_det
        else:
            caps["drviewer_detail"] = caps["drviewer_detail"] or d_det
        if p_ok:
            caps["postdata_ok"] = True
            caps["postdata_detail"] = p_det
        else:
            caps["postdata_detail"] = caps["postdata_detail"] or p_det
        if f_ok:
            caps["formviewer_ok"] = True
            caps["formviewer_detail"] = f_det
        else:
            caps["formviewer_detail"] = caps["formviewer_detail"] or f_det
    return caps


def assert_can_fill_or_raise(tokens: dict[str, str]) -> dict:
    """Allow fill if FormViewer CLS works. Rematch needs ExecuteStore OR PostData."""
    caps = probe_fill_capabilities(tokens)
    if caps["formviewer_ok"] or caps["drviewer_ok"]:
        if not caps["drviewer_ok"] and caps["formviewer_ok"]:
            if caps["postdata_ok"]:
                print(
                    "WARN: ExecuteStore 403 — rematch live bang PostData + dien FormViewer.",
                    flush=True,
                )
            else:
                print(
                    "WARN: ExecuteStore+PostData DENIED — chi dien khi da co phieukhamId "
                    "(cache/CSV). Rematch ten/CCCD bi khoa.",
                    flush=True,
                )
        return caps
    raise RuntimeError(
        "Khong dien duoc CLS: DRViewer va FormViewer deu bi chan. "
        f"DRViewer={caps['drviewer_detail']}; FormViewer={caps['formviewer_detail']}. "
        "Bo qua TK2. Can Medinet/IT cap quyen DynamicReport hoac FormViewer cho pkdkthuankieu."
    )


def assert_drviewer_or_raise(tokens: dict[str, str]) -> None:
    """Compat wrapper: prefer soft FormViewer gate; keep name for old callers."""
    assert_can_fill_or_raise(tokens)


def to_fparams(obj: dict) -> list:
    return [{"Varible": k, "Value": "" if v is None else str(v)} for k, v in obj.items()]


def api(token: str, path: str, method: str = "GET", body=None, reauth=None, extra_headers=None):
    """Call Medinet API. Optional reauth() refreshes token on 401."""
    url = f"{BE}{path}" if path.startswith("/") else path
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    last = None
    for attempt in range(5):
        hdr = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "SessionSiteId": SITE_ID,
        }
        if extra_headers:
            hdr.update(extra_headers)
        headers = medinet_http_headers(hdr)
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with _urlopen(req, timeout=180) as r:
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
    # Fasting glucose (ô Đường máu lúc đói) — Medinet form field
    "Glucose_fasting": "SinhHoaMau_DuongMauLucDoi",
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
    "SinhHoaMau_DuongMauLucDoi",
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


def _num_close(a, b, *, rel: float = 0.02, abs_tol: float = 0.05) -> bool:
    """True when two lab numbers are effectively the same."""
    try:
        fa = float(str(a).strip().replace(",", ".").lstrip("<>"))
        fb = float(str(b).strip().replace(",", ".").lstrip("<>"))
    except Exception:
        return str(a).strip() == str(b).strip()
    if fa == fb:
        return True
    return abs(fa - fb) <= max(abs_tol, rel * max(abs(fa), abs(fb), 1.0))


def _glucose_twin_key(field: str) -> str | None:
    """Định kỳ form often keeps one glucose box; LucDoi ↔ DuongMau are twins."""
    if field == "SinhHoaMau_DuongMauLucDoi":
        return "SinhHoaMau_DuongMau"
    if field == "SinhHoaMau_DuongMau":
        return "SinhHoaMau_DuongMauLucDoi"
    return None


def cls_missing_lab_fields(existing: dict | None, payload: dict) -> list[str]:
    """Lab fields in PDF payload that are empty OR wrong on the web form.

    Rule: dien theo PDF (binh thuong lan bat thuong), KE CA Urea khi PDF co.
    Also tracks LoaiKham (must be Khám định kỳ = 5152).
    Glucose: LucDoi missing is OK when DuongMau holds the same value (FormViewer
    định kỳ often only persists SinhHoaMau_DuongMau).
    """
    tracked = [
        k
        for k in payload
        if k in NUMBER_FIELDS or k in URINE_TEXT_FIELDS or k == "NuocTieu_NiTrit" or k == "LoaiKham"
    ]
    if not existing:
        return list(tracked)
    missing = []
    for k in tracked:
        sent = payload.get(k)
        got = existing.get(k)
        if k == "LoaiKham":
            try:
                if int(str(got).strip()) != int(LOAI_KHAM_DINH_KY):
                    missing.append(k)
            except Exception:
                missing.append(k)
            continue
        if got in (None, ""):
            twin = _glucose_twin_key(k)
            twin_got = existing.get(twin) if twin else None
            if (
                twin
                and twin_got not in (None, "")
                and sent not in (None, "")
                and _num_close(twin_got, sent)
            ):
                # Web stored glucose on the twin field — count as filled
                continue
            missing.append(k)
            continue
        if k in NUMBER_FIELDS and sent not in (None, ""):
            if not _num_close(got, sent):
                missing.append(k)
            continue
        if k in URINE_TEXT_FIELDS and sent == "Negative":
            gl = re.sub(r"\s+", " ", str(got).strip().lower())
            if gl not in {"negative", "neg"} and not re.search(
                r"âm\s*t[íi]nh|am\s*tinh", gl
            ):
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
    """True when PDF payload fields (incl. Urea) are missing on web.

    Do not guess from Get alone (Get often omits NuocTieu_Urobilinogen even when
    the form has it).
    """
    if not existing or not cls_has_lab_values(existing):
        return False
    if not payload:
        return False
    miss = cls_missing_lab_fields(existing, payload)
    return bool(miss)

def get_cls(token: str, phieukham_id: int | str, reauth=None) -> tuple[dict | None, str]:
    """DRViewer Get. On 403/access denied return None (caller uses FormViewer)."""
    s, d, token = api(
        token,
        f"/api/services/app/DRViewer/ExecuteStoreWithParam_ByDatasource"
        f"?dataSourceId={CLS_DATASOURCE_ID}&store={CLS_STORE_GET}",
        "POST",
        to_fparams({"phieukhamId": phieukham_id}),
        reauth=reauth,
    )
    if _is_access_denied(s, d):
        return None, token
    rows = ((d or {}).get("result") or {}).get("data") or []
    return (rows[0] if rows else None), token


def get_formviewer_cls(token: str, phieukham_id: int | str, reauth=None) -> tuple[dict | None, str]:
    """Web form path — light CLS read (works when DRViewer Get is 403).

    Prefer FormViewerDataByRecord with TTHCId UrlPage (same context as Lưu).
    Fall back to FormViewerData + phieukhamId fparams.
    """
    url_page = _cls_formviewer_urlpage(phieukham_id)
    q = urllib.parse.urlencode(
        {
            "form_id": CLS_FORM_ID,
            "SessionSiteId": SITE_ID,
            "record_id": str(phieukham_id),
            "UrlPage": url_page,
            "ispopup": "false",
            "istab": "false",
        }
    )
    s, d, token = api(
        token,
        f"/api/services/app/FormViewer/FormViewerDataByRecord?{q}",
        "POST",
        to_fparams({"TTHCId": phieukham_id, "maukham": CLS_MAUKHAM}),
        reauth=reauth,
        extra_headers={"displaymode": "0"},
    )
    if not _is_access_denied(s, d) and s == 200:
        fd = (((d or {}).get("result") or {}).get("data") or {}).get("formData") or []
        if fd:
            return (fd[0] if isinstance(fd, list) else fd), token
    # Fallback: classic FormViewerData
    s2, d2, token = api(
        token,
        f"/api/services/app/FormViewer/FormViewerData?form_id={CLS_FORM_ID}"
        f"&SessionSiteId={SITE_ID}&UrlPage=",
        "POST",
        to_fparams({"phieukhamId": phieukham_id}),
        reauth=reauth,
        extra_headers={"displaymode": "0"},
    )
    if _is_access_denied(s2, d2):
        return None, token
    fd2 = (((d2 or {}).get("result") or {}).get("data") or {}).get("formData") or []
    return (fd2[0] if fd2 else None), token


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
    """Merged Get + FormViewer row. FormViewer alone OK when DRViewer Get is 403."""
    row_g, token = get_cls(token, phieukham_id, reauth=reauth)
    row_f, token = get_formviewer_cls(token, phieukham_id, reauth=reauth)
    if not row_g and not row_f:
        return None, token
    if not row_g:
        return row_f, token
    if not row_f:
        return row_g, token
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
    *,
    retries: int = 6,
    delay_s: float = 0.7,
) -> tuple[bool, str, str]:
    """Confirm CLS is readable on the same phieukhamId the UI uses.

    Prefer merged Get+FormViewer — Get alone often returns empty even when
    the web form has values (false ERROR_IMPORT / stuck INBOX).

    Medinet/FormViewer often lags after save ("Thành công" but read empty 1–4s).
    Retry briefly before declaring failure.

    Returns (ok, detail, token).
    """
    last_detail = "Get+FormViewer empty after save"
    row = None
    attempts = max(1, int(retries))
    for attempt in range(attempts):
        if attempt:
            time.sleep(delay_s * attempt)
        row, token = load_cls_view(token, phieukham_id, reauth=reauth)
        if cls_has_lab_values(row):
            break
        last_detail = f"Get+FormViewer empty after save (try {attempt + 1}/{attempts})"
    else:
        return False, last_detail, token

    # Spot-check: EVERY lab key we sent must appear on Get+FormViewer
    # (glucose LucDoi may land on DuongMau — see cls_missing_lab_fields)
    if payload:
        miss = cls_missing_lab_fields(row, payload)
        # Urea optional only when not in payload
        miss = [k for k in miss if k != "SinhHoaMau_Ure" or "SinhHoaMau_Ure" in payload]
        if miss:
            # One more short wait then re-check
            time.sleep(delay_s)
            row2, token = load_cls_view(token, phieukham_id, reauth=reauth)
            miss2 = cls_missing_lab_fields(row2 or row, payload)
            miss2 = [k for k in miss2 if k != "SinhHoaMau_Ure" or "SinhHoaMau_Ure" in payload]
            if miss2:
                return False, f"VERIFY_FAIL missing={','.join(miss2[:12])}", token

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
    if _is_access_denied(s, d):
        msg = _api_error_message(d) or f"http={s} Access denied"
        return False, msg, {"_access_denied": True, "http": s, "body": d}, token
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


def _formviewer_write_result(status: int, body: dict | None) -> tuple[bool, str, dict]:
    """Parse FormViewer response. Soft-ok VersionType-3 is NOT success (often empty form)."""
    res = (body or {}).get("result") or {}
    if not isinstance(res, dict):
        res = {}
    ok = bool(res.get("isSucceeded"))
    code = str(res.get("code") or "")
    msg = str(res.get("message") or "")
    if _is_access_denied(status, body, msg):
        return False, msg or f"http={status} Access denied", {"http": status, "body": body}
    if (not ok) and code == "VersionType-3-Non-Insert-Id":
        # Historical: soft-ok frequently leaves web empty — do not treat as saved
        return False, f"soft-fail:{code}:{msg}", res
    if ok:
        return True, msg or f"http={status} ok", res
    return False, msg or f"http={status}", res if res else {"http": status, "body": body}


def _to_comma_decimal(val) -> str:
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return str(val)
    try:
        num = float(val) if not isinstance(val, float) else val
    except Exception:
        return str(val)
    if num.is_integer():
        return str(int(num))
    return f"{num:.6f}".rstrip("0").rstrip(".").replace(".", ",")


def _prepare_formviewer_payload(payload: dict) -> dict:
    """Shape labs for FormToDataBaseUpdate (UI Lưu thay đổi).

    - Mirror LucDoi → DuongMau when định kỳ form only binds DuongMau
    - NumberBox: JSON numbers; urine TextBox: comma decimals or Negative
    """
    out: dict = {"LoaiKham": int(LOAI_KHAM_DINH_KY)}
    luc = payload.get("SinhHoaMau_DuongMauLucDoi")
    bat = payload.get("SinhHoaMau_DuongMau")
    src = dict(payload)
    if luc not in (None, "") and bat in (None, ""):
        src["SinhHoaMau_DuongMau"] = luc
    for k, v in src.items():
        if k in ("LoaiKham", "__label_action_code", "phieukhamId", "cdId", "IsNamGioi"):
            if k == "phieukhamId":
                out[k] = v
            elif k in ("cdId", "IsNamGioi") and v not in (None, ""):
                out[k] = v
            continue
        if v in (None, ""):
            continue
        if k == "NuocTieu_NiTrit":
            try:
                out[k] = int(v)
            except Exception:
                continue
            continue
        if k in URINE_TEXT_FIELDS:
            if v == "Negative" or str(v).strip().lower() == "negative":
                out[k] = "Negative"
            else:
                try:
                    out[k] = _to_comma_decimal(v)
                except Exception:
                    continue
            continue
        if k in NUMBER_FIELDS:
            num = _to_number(v)
            if num is not None:
                out[k] = num
            continue
        num = _to_number(v)
        if num is not None:
            out[k] = num
    return out


def _formviewer_open_cls(token: str, record_id: int | str, reauth=None):
    """Open CLS form context (CREATE_PHIEU,SAVE,BACK) like the browser."""
    url_page = _cls_formviewer_urlpage(record_id)
    q = urllib.parse.urlencode(
        {
            "form_id": CLS_FORM_ID,
            "SessionSiteId": SITE_ID,
            "UrlPage": url_page,
            "ispopup": "false",
            "istab": "false",
        }
    )
    params = [
        {"Varible": "TTHCId", "Value": str(record_id)},
        {"Varible": "maukham", "Value": CLS_MAUKHAM},
        {"Varible": "KSKDK_Phieu_CanLamSang_guid", "Value": str(uuid.uuid4())},
        {"Varible": "formdata_parent", "Value": "null"},
        {
            "Varible": "DataFlowData",
            "Value": json.dumps(
                {
                    "LoaiKham": LOAI_KHAM_DINH_KY,
                    "__label_action_code": "CREATE_PHIEU,SAVE,BACK",
                },
                ensure_ascii=False,
            ),
        },
    ]
    s, d, token = api(
        token,
        f"/api/services/app/FormViewer/FormViewerData?{q}",
        "POST",
        params,
        reauth=reauth,
        extra_headers={"displaymode": "0"},
    )
    return s, d, token


def _formviewer_update_cls(token: str, payload: dict, reauth=None):
    """Persist CLS via FormToDataBaseUpdate?record_id= (UI Lưu thay đổi)."""
    record_id = payload.get("phieukhamId")
    url_page = _cls_formviewer_urlpage(record_id)
    q = urllib.parse.urlencode(
        {
            "form_id": CLS_FORM_ID,
            "record_id": str(record_id),
            "SessionSiteId": SITE_ID,
            "UrlPage": url_page,
            "ispopup": "false",
            "istab": "false",
        }
    )
    body = {k: v for k, v in payload.items() if k != "phieukhamId"}
    s, d, token = api(
        token,
        f"/api/services/app/FormViewer/FormToDataBaseUpdate?{q}",
        "POST",
        body,
        reauth=reauth,
        extra_headers={"displaymode": "0"},
    )
    ok, msg, res = _formviewer_write_result(s, d)
    return ok, msg, res, token


def _formviewer_insert_cls(token: str, payload: dict, reauth=None):
    """Fallback Insert when Update has no row yet (rare for existing TTHC)."""
    record_id = payload.get("phieukhamId")
    url_page = _cls_formviewer_urlpage(record_id)
    q = urllib.parse.urlencode(
        {
            "form_id": CLS_FORM_ID,
            "UrlPage": url_page,
            "SessionSiteId": SITE_ID,
            "ispopup": "false",
            "istab": "false",
        }
    )
    body = {k: v for k, v in payload.items() if k != "phieukhamId"}
    s, d, token = api(
        token,
        f"/api/services/app/FormViewer/FormToDatabaseInsert?{q}",
        "POST",
        body,
        reauth=reauth,
        extra_headers={"displaymode": "0"},
    )
    ok, msg, res = _formviewer_write_result(s, d)
    return ok, msg, res, token


def _formviewer_field_retry(token: str, payload: dict, reauth=None):
    """If bulk Update fails, send key NumberBox fields one-by-one then re-check."""
    record_id = payload.get("phieukhamId")
    url_page = _cls_formviewer_urlpage(record_id)
    q = urllib.parse.urlencode(
        {
            "form_id": CLS_FORM_ID,
            "record_id": str(record_id),
            "SessionSiteId": SITE_ID,
            "UrlPage": url_page,
            "ispopup": "false",
            "istab": "false",
        }
    )
    path = f"/api/services/app/FormViewer/FormToDataBaseUpdate?{q}"
    ok_n = 0
    last_res: dict = {}
    last_msg = ""
    # Blood + chemistry first (what empty screenshot shows missing)
    keys = [
        k
        for k in payload
        if k in NUMBER_FIELDS or k in URINE_TEXT_FIELDS or k == "NuocTieu_NiTrit"
    ]
    keys.sort(key=lambda k: (0 if k in NUMBER_FIELDS else 1, k))
    for k in keys:
        solo = {"LoaiKham": LOAI_KHAM_DINH_KY, k: payload[k]}
        s, d, token = api(
            token,
            path,
            "POST",
            solo,
            reauth=reauth,
            extra_headers={"displaymode": "0"},
        )
        ok, msg, res = _formviewer_write_result(s, d)
        last_msg, last_res = msg, res
        if ok:
            ok_n += 1
    return ok_n, last_msg, last_res, token


def _formviewer_save_cls(token: str, payload: dict, reauth=None):
    """Persist CLS like UI Lưu thay đổi. Only when DRViewer Set is access-denied.

    Steps (proven in historical cls-import):
      1) FormViewerData open with DataFlowData + SAVE action
      2) FormToDataBaseUpdate?record_id=TTHCId with lab body
      3) Field-by-field retry if still empty on FormViewerData read
    Soft-ok alone is never treated as success.
    """
    if "phieukhamId" not in payload:
        return False, "missing phieukhamId", {}, token
    record_id = payload["phieukhamId"]
    body = _prepare_formviewer_payload(payload)
    body["phieukhamId"] = record_id

    # 1) Open form context
    s_open, d_open, token = _formviewer_open_cls(token, record_id, reauth=reauth)
    if _is_access_denied(s_open, d_open):
        return (
            False,
            f"FormViewer open Access denied http={s_open}",
            {"open": d_open},
            token,
        )

    # 2) Bulk Update (Lưu thay đổi)
    ok_u, msg_u, res_u, token = _formviewer_update_cls(token, body, reauth=reauth)
    row, token = get_formviewer_cls(token, record_id, reauth=reauth)
    if ok_u and cls_has_lab_values(row):
        return True, f"UPDATE-fallback:{msg_u}", {"update": res_u, "open": d_open}, token

    # 3) Insert then Update again (new CLS phiếu)
    ok_i, msg_i, res_i, token = _formviewer_insert_cls(token, body, reauth=reauth)
    if ok_i:
        ok_u2, msg_u2, res_u2, token = _formviewer_update_cls(token, body, reauth=reauth)
        row, token = get_formviewer_cls(token, record_id, reauth=reauth)
        if cls_has_lab_values(row):
            return (
                True,
                f"INSERT+UPDATE:{msg_i};{msg_u2}",
                {"insert": res_i, "update": res_u2, "open": d_open},
                token,
            )

    # 4) Field-by-field
    ok_n, msg_f, res_f, token = _formviewer_field_retry(token, body, reauth=reauth)
    time.sleep(0.4)
    row, token = get_formviewer_cls(token, record_id, reauth=reauth)
    if cls_has_lab_values(row):
        return (
            True,
            f"FIELD-fallback:n={ok_n}:{msg_f}",
            {"fields": res_f, "update": res_u, "insert": res_i, "open": d_open},
            token,
        )

    return (
        False,
        f"FormViewer empty after save UPDATE:{msg_u}; INSERT:{msg_i}; FIELDS:{ok_n}:{msg_f}",
        {"update": res_u, "insert": res_i, "fields": res_f, "open": d_open},
        token,
    )


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
    """Save CLS via store Set; on DRViewer 403 fall back to FormViewer (light).

    Prefer KSKDK_Phieu_CanLamSang_Set with phieukhamId.
    Access denied → FormToDatabaseInsert / FormToDataBaseUpdate (TTHC-style).
    FormViewer is NOT used for urine-format errors (those stay on Set retries).

    On urine-format errors: keep blood + Nitrit, and retry urine TextBox fields
    one-by-one so Âm tính→Negative values are still saved. Never treat
    "strip all urine" as a full success (that left web missing nước tiểu).
    """
    if "phieukhamId" not in payload:
        return False, "missing phieukhamId", {}, token

    # Ensure urine text is only number or exact "Negative" before first Set
    clean = dict(payload)
    clean["LoaiKham"] = int(LOAI_KHAM_DINH_KY)
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

    # Light path: DRViewer Set blocked → FormViewer (do not use for urine format)
    if (isinstance(res, dict) and res.get("_access_denied")) or _is_access_denied(
        None, res if isinstance(res, dict) else None, msg
    ):
        return _formviewer_save_cls(token, clean, reauth=reauth)

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
