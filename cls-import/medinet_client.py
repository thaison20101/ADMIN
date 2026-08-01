#!/usr/bin/env python3
"""Shared Medinet API client with cookie+Bearer auth."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
from typing import Any, Dict, List, Optional

API = "https://be-qlskcd.medinet.org.vn"
DEFAULT_SITE = 130


class MedinetClient:
    def __init__(self, username: str, password: str, site_id: int = DEFAULT_SITE):
        self.username = username
        self.password = password
        self.site_id = site_id
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.token = ""
        self.login()

    def login(self) -> str:
        body = json.dumps(
            {"userNameOrEmailAddress": self.username, "password": self.password}
        ).encode()
        req = urllib.request.Request(
            f"{API}/api/TokenAuth/Authenticate",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with self.opener.open(req, timeout=60) as r:
            auth = json.loads(r.read().decode())["result"]
        self.token = auth["accessToken"]
        return self.token

    def call(self, method: str, url: str, body: Any = None, retries: int = 3) -> Dict[str, Any]:
        last_err: Optional[Exception] = None
        for attempt in range(retries):
            data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                method=method,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "SessionSiteId": str(self.site_id),
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "displaymode": "0",
                },
            )
            try:
                with self.opener.open(req, timeout=180) as r:
                    raw = r.read().decode("utf-8", "ignore")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "ignore")
                if e.code in (401, 403, 429, 502, 503) and attempt < retries - 1:
                    time.sleep(1.2 * (attempt + 1))
                    if e.code == 401:
                        self.login()
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = {"raw": raw[:500]}
                raise RuntimeError(f"HTTP {e.code}: {payload}") from e
            except Exception as e:
                last_err = e
                time.sleep(0.8 * (attempt + 1))
        raise RuntimeError(f"call failed: {last_err}")

    def post_data(
        self,
        report_id: int,
        url_code: str,
        filters: Dict[str, Any],
        page: int = 1,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        url_page = urllib.parse.quote(
            f"/app/main/dynamicreport/report/viewer-utility/{url_code}"
        )
        params = [{"Varible": k, "Value": v} for k, v in filters.items()]
        params += [
            {"Varible": "ReportId", "Value": report_id},
            {"Varible": "PageSize", "Value": page_size},
            {"Varible": "PageNumber", "Value": page},
            {"Varible": "PageDefaultFilter", "Value": None},
        ]
        url = (
            f"{API}/api/services/app/DRViewer/PostDataWithDataOutput?"
            f"id={report_id}&SessionSiteId={self.site_id}&UrlPage={url_page}&ispopup=false&istab=false"
        )
        res = self.call("POST", url, params)
        data = (res.get("result") or {}).get("data")
        return data if isinstance(data, list) else []

    def fetch_all(
        self,
        report_id: int,
        url_code: str,
        filters: Dict[str, Any],
        page_size: int = 100,
        max_pages: int = 200,
    ) -> List[Dict[str, Any]]:
        all_rows: List[Dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            rows = self.post_data(report_id, url_code, filters, page=page, page_size=page_size)
            if not rows:
                break
            all_rows.extend(rows)
            print(f"  {url_code} page {page}: +{len(rows)} total={len(all_rows)}")
            if len(rows) < page_size:
                break
            time.sleep(0.15)
        return all_rows
