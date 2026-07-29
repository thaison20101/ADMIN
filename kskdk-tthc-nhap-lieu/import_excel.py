#!/usr/bin/env python3
"""Import file Excel KSKDK_TTHC lên hệ thống (thay cho chức năng Import thiếu trên web).

Đăng nhập bằng tài khoản của bạn → map Name/Id danh mục → gọi FormToDatabaseInsert.
KHÔNG lưu mật khẩu trong source code / git.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import load_workbook

API = "https://be-qlskcd.medinet.org.vn"
FORM_CODE = "KSKDK_TTHC"
FORM_ID = 1000092
URL_PAGE = "/nav_group/kskdk_thongtinkham/app/main/dynamicform/viewer/KSKDK_TTHC"
DEFAULT_SITE = 130

# Excel header → API field
COL_MAP = {
    "NgayKham": "NgayKham",
    "DoiTuong": "DoiTuong_M13",
    "DiaDiemKham": "DoiTuongKham",
    "HinhThucChiTra": "HinhThucChiTraKhamSK",
    "HinhThucKham": "HinhThucChiTraKhamSK_ChiTiet",
    "NguonKhac_GhiRo": "NguonKhac_GhiRo",
    "CCCD": "DinhDanhCaNhan",
    "HoTen": "HoTen",
    "NgaySinh": "NgaySinh",
    "GioiTinh": "GioiTinh",
    "DanToc": "DanTocId",
    "NhomMau": "NhomMauId",
    "YeuToNhomMau": "YeuToNhomMauId",
    "BHYT": "BHYT",
    "SDT": "SDT",
    "NoiOHienTai": "DiaChiHienTai",
    "TinhThanh": "DiaChiHienTai_Tinh",
    "XaPhuong": "DiaChiHienTai_XaPhuong",
    "NgheNghiepId": "NgheNghiepId",
    "NgheNghiep": "NgheNghiep",
    "NoiCongTac": "NoiCongTac",
    "XaPhuongCongTac": "NoiCongTac_XaPhuong",
    "LyDoKham": "LyDoKham",
}

# Fields that should be resolved via lookup Name→Id
LOOKUP_FIELDS = {
    "DoiTuong_M13": 1000195,
    "DoiTuongKham": 1000198,
    "HinhThucChiTraKhamSK": 1000190,
    "HinhThucChiTraKhamSK_ChiTiet": 1000265,
    "GioiTinh": 1000056,
    "DanTocId": 1000266,
    "NhomMauId": 1000260,
    "YeuToNhomMauId": 1000261,
    "DiaChiHienTai_Tinh": 1001337,
    "NoiCongTac": 1000292,
}


def load_indexes_from_excel(path: Path) -> Dict[str, LookupIndex]:
    """Đọc danh mục từ các sheet DM_* trong file Excel (ổn định hơn gọi lại API lookup)."""
    wb = load_workbook(path, data_only=True)
    sheet_map = {
        "DoiTuong_M13": "DM_DoiTuong",
        "DoiTuongKham": "DM_DiaDiemKham",
        "HinhThucChiTraKhamSK": "DM_HinhThucChiTra",
        "HinhThucChiTraKhamSK_ChiTiet": "DM_HinhThucKham",
        "GioiTinh": "DM_GioiTinh",
        "DanTocId": "DM_DanToc",
        "NhomMauId": "DM_NhomMau",
        "YeuToNhomMauId": "DM_YeuToNhomMau",
        "DiaChiHienTai_Tinh": "DM_TinhThanh",
        "NoiCongTac": "DM_NoiCongTac",
    }
    indexes: Dict[str, LookupIndex] = {}
    for api_key, sheet_name in sheet_map.items():
        if sheet_name not in wb.sheetnames:
            indexes[api_key] = LookupIndex([])
            continue
        ws = wb[sheet_name]
        items = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] is None and row[1] is None:
                continue
            items.append({"Id": row[0], "Name": row[1]})
        indexes[api_key] = LookupIndex(items)
    # Xã phường mặc định từ sheet (theo HCM); nếu đổi tỉnh sẽ refetch
    if "DM_XaPhuong" in wb.sheetnames:
        items = []
        for row in wb["DM_XaPhuong"].iter_rows(min_row=2, values_only=True):
            if row[0] is None and row[1] is None:
                continue
            items.append({"Id": row[0], "Name": row[1]})
        indexes["_XaPhuongDefault"] = LookupIndex(items)
    else:
        indexes["_XaPhuongDefault"] = LookupIndex([])
    return indexes


def http_json(
    method: str,
    url: str,
    token: str,
    site_id: int,
    body: Any = None,
    timeout: int = 90,
    retries: int = 2,
) -> Dict[str, Any]:
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {token}",
                "SessionSiteId": str(site_id),
                "displaymode": "0",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "ignore")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "ignore")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"raw": raw[:1000]}
            last_err = RuntimeError(f"HTTP {e.code} {url}: {payload}")
            if e.code in (401, 403, 429, 502, 503) and attempt < retries:
                time.sleep(0.8 * (attempt + 1))
                continue
            raise last_err from e
    raise last_err or RuntimeError("http_json failed")


def login(username: str, password: str) -> str:
    url = f"{API}/api/TokenAuth/Authenticate"
    payload = {"userNameOrEmailAddress": username, "password": password}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    if not res.get("success"):
        raise RuntimeError(f"Đăng nhập thất bại: {res.get('error') or res}")
    return res["result"]["accessToken"]


def resolve_site(token: str) -> int:
    url = f"{API}/api/services/app/User/GetSessionSiteByViewCode?viewType=form&viewCode={FORM_CODE}"
    for site in (0, DEFAULT_SITE):
        try:
            res = http_json("GET", url, token, site)
            data = (res.get("result") or {}).get("data")
            if data not in (None, "", 0, "0"):
                return int(data)
        except Exception:
            continue
    return DEFAULT_SITE


def hf(token: str, site_id: int, service_id: int, params: Optional[list] = None) -> list:
    qs = urllib.parse.urlencode({"serviceId": service_id, "SessionSiteId": site_id})
    url = f"{API}/api/services/app/DRReportService/HF_ExecuteServiceWithParam?{qs}"
    res = http_json("POST", url, token, site_id, params or [])
    data = (res.get("result") or {}).get("data")
    return data if isinstance(data, list) else []


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D")
    return s


def normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(str(s)).strip().lower())


class LookupIndex:
    def __init__(self, items: List[Dict[str, Any]]):
        self.by_id: Dict[str, Any] = {}
        self.by_name: Dict[str, Any] = {}
        for it in items:
            iid = it.get("Id")
            name = it.get("Name")
            if iid is not None:
                self.by_id[str(iid)] = iid
            if name is not None:
                self.by_name[normalize_name(name)] = iid
                self.by_name[normalize_name(str(name).strip())] = iid

    def resolve(self, value: Any) -> Any:
        if value is None or str(value).strip() == "":
            return None
        s = str(value).strip()
        if s in self.by_id:
            return self.by_id[s]
        if s.isdigit() and s in self.by_id:
            return self.by_id[s]
        key = normalize_name(s)
        if key in self.by_name:
            return self.by_name[key]
        # partial contains
        for n, iid in self.by_name.items():
            if key == n or key in n or n in key:
                return iid
        raise KeyError(f"Không map được giá trị '{value}'")


def parse_date(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).strftime("%Y-%m-%dT00:00:00")
    s = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    # excel serial?
    try:
        n = float(s)
        # openpyxl usually gives datetime already; skip serial edge cases
    except Exception:
        pass
    raise ValueError(f"Ngày không hợp lệ: {value}")


def read_excel_rows(path: Path) -> List[Dict[str, Any]]:
    wb = load_workbook(path, data_only=True)
    if "NhapLieu" not in wb.sheetnames:
        raise RuntimeError("File Excel thiếu sheet NhapLieu")
    ws = wb["NhapLieu"]
    headers = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    rows: List[Dict[str, Any]] = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        # skip hint row (row 2) if first cell looks like instruction
        values = list(row)
        if i == 2 and values and isinstance(values[0], str) and "dd/MM" in values[0]:
            continue
        item: Dict[str, Any] = {}
        empty = True
        for h, v in zip(headers, values):
            if not h or h not in COL_MAP:
                continue
            if v is not None and str(v).strip() != "":
                empty = False
            item[h] = v
        if empty:
            continue
        # skip sample placeholder if user left it unchanged? keep — user may want it
        rows.append(item)
    return rows


def build_payload(row: Dict[str, Any], indexes: Dict[str, LookupIndex], token: str, site_id: int) -> Dict[str, Any]:
    raw: Dict[str, Any] = {}
    for excel_key, api_key in COL_MAP.items():
        if excel_key not in row:
            continue
        val = row[excel_key]
        if val is None or str(val).strip() == "":
            continue
        raw[api_key] = val

    payload: Dict[str, Any] = {}

    for dk in ("NgayKham", "NgaySinh"):
        if dk in raw:
            payload[dk] = parse_date(raw[dk])

    for tk in ("NguonKhac_GhiRo", "DinhDanhCaNhan", "HoTen", "BHYT", "SDT", "DiaChiHienTai", "NgheNghiep", "LyDoKham"):
        if tk in raw:
            payload[tk] = str(raw[tk]).strip()
            if tk == "HoTen":
                payload[tk] = payload[tk].upper()

    if "HoTen" in payload:
        payload["HoTenKhongDau"] = strip_accents(payload["HoTen"]).upper()

    if "NgheNghiepId" in raw and str(raw["NgheNghiepId"]).strip() != "":
        payload["NgheNghiepId"] = int(raw["NgheNghiepId"]) if str(raw["NgheNghiepId"]).isdigit() else raw["NgheNghiepId"]
    elif "NgheNghiep" in payload and payload["NgheNghiep"]:
        # Resolve Id bằng SearchValue (danh mục nghề nghiệp rất lớn, không load hết vào Excel)
        try:
            items = hf(
                token,
                site_id,
                1000294,
                [{"Varible": "SearchValue", "Value": payload["NgheNghiep"]}],
            )
            idx = LookupIndex(items)
            payload["NgheNghiepId"] = idx.resolve(payload["NgheNghiep"])
            # Chuẩn hóa lại tên theo danh mục
            for it in items:
                if it.get("Id") == payload["NgheNghiepId"]:
                    payload["NgheNghiep"] = it.get("Name") or payload["NgheNghiep"]
                    break
        except Exception as e:
            raise ValueError(
                f"NgheNghiep: không tìm thấy '{payload['NgheNghiep']}' trong danh mục. "
                f"Hãy điền đúng tên nghề hoặc Id vào cột NgheNghiepId. ({e})"
            ) from e

    for api_key in LOOKUP_FIELDS:
        if api_key not in raw:
            continue
        idx = indexes.get(api_key) or LookupIndex([])
        try:
            payload[api_key] = idx.resolve(raw[api_key])
        except KeyError as e:
            raise ValueError(f"{api_key}: {e}") from e

    def resolve_xa(field_name: str) -> None:
        if field_name not in raw:
            return
        # Ưu tiên danh mục trong Excel; nếu fail và có token thì gọi API theo tỉnh
        default_idx = indexes.get("_XaPhuongDefault") or LookupIndex([])
        try:
            payload[field_name] = default_idx.resolve(raw[field_name])
            return
        except KeyError:
            pass
        tinh_id = payload.get("DiaChiHienTai_Tinh") or 50
        try:
            xa_items = hf(token, site_id, 1000058, [{"Varible": "Id", "Value": tinh_id}])
            payload[field_name] = LookupIndex(xa_items).resolve(raw[field_name])
        except Exception as e:
            raise ValueError(f"{field_name}: không map được '{raw[field_name]}' ({e})") from e

    resolve_xa("DiaChiHienTai_XaPhuong")
    resolve_xa("NoiCongTac_XaPhuong")

    if payload.get("DinhDanhCaNhan"):
        payload.setdefault("CoCCCD", 264)

    return payload


def insert_one(token: str, site_id: int, form_data: Dict[str, Any]) -> Dict[str, Any]:
    qs = urllib.parse.urlencode(
        {
            "form_id": FORM_ID,
            "UrlPage": URL_PAGE,
            "ispopup": "false",
            "istab": "false",
        }
    )
    url = f"{API}/api/services/app/FormViewer/FormToDatabaseInsert?{qs}"
    return http_json("POST", url, token, site_id, form_data)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Import Excel lên form KSKDK_TTHC")
    p.add_argument("--excel", required=True, help="Đường dẫn file Excel NhapLieu")
    p.add_argument("--user", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--site-id", type=int, default=None)
    p.add_argument("--delay", type=float, default=0.4)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-sample", action="store_true", help="Bỏ dòng mẫu NGUYEN VAN A")
    p.add_argument("--out", default="import_result.jsonl")
    args = p.parse_args(argv)

    token = login(args.user, args.password)
    site_id = args.site_id or resolve_site(token)
    print(f"Đăng nhập OK — user={args.user}, SessionSiteId={site_id}")

    indexes = load_indexes_from_excel(Path(args.excel))
    for k, idx in indexes.items():
        print(f"  danh mục {k}: {len(idx.by_id)} items")

    rows = read_excel_rows(Path(args.excel))
    if args.skip_sample:
        rows = [r for r in rows if str(r.get("HoTen") or "").strip().upper() != "NGUYEN VAN A"]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        print("Không có dòng dữ liệu để import.", file=sys.stderr)
        return 2

    ok = fail = 0
    with open(args.out, "w", encoding="utf-8") as log:
        for i, row in enumerate(rows, start=1):
            try:
                payload = build_payload(row, indexes, token, site_id)
                if args.dry_run:
                    res = {"dry_run": True, "payload": payload}
                    print(f"[{i}/{len(rows)}] DRY-RUN {payload.get('HoTen')}")
                else:
                    # Re-login nhẹ nếu token bị invalid giữa chừng
                    try:
                        res = insert_one(token, site_id, payload)
                    except RuntimeError as e:
                        if "HTTP 401" in str(e):
                            token = login(args.user, args.password)
                            res = insert_one(token, site_id, payload)
                        else:
                            raise
                    succeeded = True
                    if isinstance(res.get("result"), dict):
                        succeeded = bool(res["result"].get("isSucceeded", res.get("success")))
                        if not succeeded:
                            raise RuntimeError(res["result"].get("message") or res)
                    print(f"[{i}/{len(rows)}] OK {payload.get('HoTen')}")
                ok += 1
                log.write(json.dumps({"index": i, "ok": True, "row": row, "payload": payload, "response": res}, ensure_ascii=False, default=str) + "\n")
            except Exception as e:
                fail += 1
                print(f"[{i}/{len(rows)}] FAIL {row.get('HoTen')}: {e}", file=sys.stderr)
                log.write(json.dumps({"index": i, "ok": False, "row": row, "error": str(e)}, ensure_ascii=False, default=str) + "\n")
            if args.delay > 0 and not args.dry_run:
                time.sleep(args.delay)

    print(f"Xong: ok={ok}, fail={fail}, log={args.out}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
