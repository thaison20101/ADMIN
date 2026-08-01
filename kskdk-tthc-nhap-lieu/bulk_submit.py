#!/usr/bin/env python3
"""Gửi hàng loạt dữ liệu CSV lên form KSKDK_TTHC (Thông tin hành chính).

Yêu cầu: token + SessionSiteId lấy từ phiên đăng nhập của bạn (xem README).
Không lưu mật khẩu trong file này.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


DEFAULT_API = "https://be-qlskcd.medinet.org.vn"
DEFAULT_FORM_CODE = "KSKDK_TTHC"
DEFAULT_FORM_ID = 1000092
DEFAULT_URL_PAGE = (
    "/nav_group/kskdk_thongtinkham/app/main/dynamicform/viewer/KSKDK_TTHC"
)


def http_json(
    method: str,
    url: str,
    token: str,
    site_id: str,
    body: Any = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "SessionSiteId": str(site_id),
        "displaymode": "0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
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
        raise RuntimeError(f"HTTP {e.code} {url}: {payload}") from e


def resolve_form_id(api: str, token: str, site_id: str, form_code: str) -> int:
    url = f"{api}/api/services/app/FormViewer/GetFormIdByFormCode?code={urllib.parse.quote(form_code)}"
    res = http_json("GET", url, token, site_id)
    data = (res.get("result") or {}).get("data")
    if data is None:
        raise RuntimeError(f"Không lấy được form id: {res}")
    return int(data)


def read_csv_rows(path: str, skip_after_header: int = 1) -> List[Dict[str, str]]:
    """Đọc CSV. Userscript export: dòng1=dataField, dòng2=label → mặc định bỏ 1 dòng sau header."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    headers = [h.strip() for h in rows[0]]
    body = rows[1 + max(0, skip_after_header) :]
    out: List[Dict[str, str]] = []
    for row in body:
        item = {}
        for idx, key in enumerate(headers):
            if not key:
                continue
            item[key] = row[idx].strip() if idx < len(row) else ""
        if not any(v for v in item.values()):
            continue
        out.append(item)
    return out


def insert_row(
    api: str,
    token: str,
    site_id: str,
    form_id: int,
    url_page: str,
    form_data: Dict[str, Any],
    dry_run: bool = False,
) -> Dict[str, Any]:
    qs = urllib.parse.urlencode(
        {
            "form_id": form_id,
            "UrlPage": url_page,
            "ispopup": "false",
            "istab": "false",
        }
    )
    url = f"{api}/api/services/app/FormViewer/FormToDatabaseInsert?{qs}"
    if dry_run:
        return {"dry_run": True, "url": url, "body": form_data}
    return http_json("POST", url, token, site_id, form_data)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Bulk submit CSV lên KSKDK_TTHC")
    p.add_argument("--csv", required=True, help="Đường dẫn file CSV UTF-8")
    p.add_argument("--token", required=True, help="Bearer access token (đã đăng nhập)")
    p.add_argument("--site-id", required=True, help="PORTAL_SESSIONSITEID")
    p.add_argument("--api", default=DEFAULT_API)
    p.add_argument("--form-code", default=DEFAULT_FORM_CODE)
    p.add_argument("--form-id", type=int, default=None)
    p.add_argument("--url-page", default=DEFAULT_URL_PAGE)
    p.add_argument("--delay", type=float, default=0.35, help="Giãn cách giữa các bản ghi (giây)")
    p.add_argument("--limit", type=int, default=0, help="Chỉ gửi N dòng đầu (0 = tất cả)")
    p.add_argument(
        "--skip-after-header",
        type=int,
        default=1,
        help="Bỏ N dòng sau header (mặc định 1 = bỏ dòng nhãn của file export)",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out", default="bulk_submit_result.jsonl")
    args = p.parse_args(argv)

    form_id = args.form_id or resolve_form_id(args.api, args.token, args.site_id, args.form_code)
    rows = read_csv_rows(args.csv, skip_after_header=args.skip_after_header)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        print("CSV không có dòng dữ liệu.", file=sys.stderr)
        return 2

    print(f"Form id={form_id}, rows={len(rows)}, dry_run={args.dry_run}")
    ok = 0
    fail = 0
    with open(args.out, "w", encoding="utf-8") as log:
        for i, row in enumerate(rows, start=1):
            try:
                res = insert_row(
                    args.api,
                    args.token,
                    args.site_id,
                    form_id,
                    args.url_page,
                    row,
                    dry_run=args.dry_run,
                )
                ok += 1
                log.write(json.dumps({"index": i, "ok": True, "row": row, "response": res}, ensure_ascii=False) + "\n")
                print(f"[{i}/{len(rows)}] OK")
            except Exception as e:
                fail += 1
                log.write(json.dumps({"index": i, "ok": False, "row": row, "error": str(e)}, ensure_ascii=False) + "\n")
                print(f"[{i}/{len(rows)}] FAIL: {e}", file=sys.stderr)
            if args.delay > 0 and not args.dry_run:
                time.sleep(args.delay)

    print(f"Xong: ok={ok}, fail={fail}, log={args.out}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
