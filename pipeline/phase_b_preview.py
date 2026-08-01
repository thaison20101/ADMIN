#!/usr/bin/env python3
"""Phase B step 1: parse PDFs → Excel preview + missing/updated lists.

Does NOT import to Medinet yet. Run this first so you can verify values/units.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()

from pdf_extract import extract_pdf  # noqa: E402

DEFAULT_CONFIG = ROOT / "pipeline" / "config.example.json"
LOCAL_CONFIG = ROOT / "pipeline" / "config.local.json"

LAB_COLS = [
    "WBC",
    "Neutrophils_pct",
    "Neutrophils_count",
    "Eosinophils_pct",
    "Eosinophils_count",
    "Monocytes_pct",
    "Monocytes_count",
    "Basophils_pct",
    "Basophils_count",
    "Lymphocytes_pct",
    "Lymphocytes_count",
    "RBC",
    "HGB",
    "HCT",
    "MCV",
    "MCH",
    "MCHC",
    "RDW",
    "PLT",
    "MPV",
    "Glucose",
    "Urea",
    "Creatinine",
    "AST",
    "ALT",
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
]


def load_config() -> dict:
    path = LOCAL_CONFIG if LOCAL_CONFIG.exists() else DEFAULT_CONFIG
    with path.open(encoding="utf-8-sig") as f:
        return json.load(f)


def _resolve_existing_build(raw: str) -> Path:
    """Prefer an existing Drive build folder; try common Google Drive name variants."""
    candidates = []
    if raw:
        candidates.append(Path(raw))
    # Common Google Drive Desktop folder names on Windows
    for drive in ("G:", "H:", "D:"):
        for mid in (
            "Drive của tôi",
            "Drive của Tôi",
            "My Drive",
            "Drive cua toi",
        ):
            candidates.append(Path(f"{drive}/{mid}/build for Supper Data"))
    candidates.append(ROOT / "pipeline" / "work" / "build")

    seen = set()
    for p in candidates:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            if p.exists():
                return p
        except Exception:
            continue
    # default: configured/raw even if missing (will be created)
    return Path(raw) if raw else candidates[0]


def build_root(cfg: dict) -> Path:
    raw = cfg.get("drive", {}).get("build_root") or r"G:\Drive của tôi\build for Supper Data"
    p = _resolve_existing_build(str(raw))
    for sub in ("excel_preview", "missing_or_updated", "logs", "cases_snapshot"):
        (p / sub).mkdir(parents=True, exist_ok=True)
    return p


def inbox_dir(cfg: dict) -> Path:
    sync = Path(cfg.get("drive", {}).get("local_sync_root") or "")
    if sync.exists():
        return sync / cfg["drive"]["inbox_folder"]
    return ROOT / "INBOX_CLS"


def list_pdfs(inbox: Path, limit: int | None) -> list[Path]:
    files = sorted([p for p in inbox.rglob("*.pdf") if p.is_file()])
    if limit:
        files = files[:limit]
    return files


def authenticate(user: str, password: str) -> str:
    BE = "https://be-qlskcd.medinet.org.vn"
    req = urllib.request.Request(
        f"{BE}/api/TokenAuth/Authenticate",
        data=json.dumps(
            {"userNameOrEmailAddress": user, "password": password, "rememberClient": True}
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["result"]["accessToken"]


def to_fparams(obj: dict) -> list:
    return [{"Varible": k, "Value": "" if v is None else str(v)} for k, v in obj.items()]


def api(token: str, path: str, method: str = "GET", body=None):
    BE = "https://be-qlskcd.medinet.org.vn"
    url = f"{BE}{path}" if path.startswith("/") else path
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "SessionSiteId": "130",
    }
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            if e.code == 401 and attempt < 3:
                time.sleep(1)
                continue
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, {"error": raw[:500]}
        except Exception as e:
            time.sleep(1 + attempt)
            last = e
    return 0, {"error": str(last)}


def fetch_unit_index(token: str, date_from: str, date_to: str) -> dict:
    """Build lookup by normalized name+phone and SID-ish MaPhieu for M3/M4."""
    reports = [
        ("M3", "KSKDK_DanhSach_KSK_M13", "NgayTao"),
        ("M4", "KSKDK_DanhSach_KSK_NguoiCaoTuoi_Report", "KSKDK_NgayKham"),
    ]
    index = {"by_phone": {}, "by_name_year": {}, "by_maphieu": {}, "no_cls_ids": set(), "all_ids": set()}

    def get_report(code):
        s, d = api(token, f"/api/services/app/DRReport/GetIdByCode?Code={code}&SessionSiteId=130")
        items = ((d or {}).get("result") or {}).get("data") or []
        return items[0] if items else None

    # day split within month range for reliability
    from datetime import date, timedelta

    def parse_d(s):
        dd, mm, yy = s.split("/")
        return date(int(yy), int(mm), int(dd))

    d0, d1 = parse_d(date_from), parse_d(date_to)
    days = []
    cur = d0
    while cur <= d1:
        days.append(cur)
        cur += timedelta(days=1)

    for mau, code, date_field in reports:
        rep = get_report(code)
        if not rep:
            safe_print(f"  report missing {code}")
            continue
        store, ds = rep["sqlContent"], rep["dataSourceId"]
        safe_print(f"Indexing {mau} ({code}) ...", flush=True)
        for day in days:
            dr = f"{day.strftime('%d/%m/%Y')} - {day.strftime('%d/%m/%Y')}"
            # all
            s, d = api(
                token,
                f"/api/services/app/DRViewer/ExecuteStoreWithParam_ByDatasource?dataSourceId={ds}&store={store}",
                "POST",
                to_fparams(
                    {
                        date_field: dr,
                        "NgayTao": dr,
                        "KSKDK_NgayKham": dr,
                        "page": 1,
                        "pageSize": 5000,
                    }
                ),
            )
            rows = ((d or {}).get("result") or {}).get("data") or []
            for r in rows:
                pid = r.get("phieukhamId") or r.get("Id")
                index["all_ids"].add(pid)
                phone = re.sub(r"\D", "", str(r.get("SDT") or ""))
                name = (r.get("HoTen") or "").strip().upper()
                ns = str(r.get("NgaySinh") or "")[:10]
                year = ns[:4] if ns else ""
                mp = str(r.get("MaPhieu") or "")
                rec = {**r, "_mau": mau}
                if phone:
                    index["by_phone"].setdefault(phone, []).append(rec)
                if name and year:
                    index["by_name_year"].setdefault(f"{name}|{year}", []).append(rec)
                if mp:
                    index["by_maphieu"][mp] = rec

            # no CLS
            s, d = api(
                token,
                f"/api/services/app/DRViewer/ExecuteStoreWithParam_ByDatasource?dataSourceId={ds}&store={store}",
                "POST",
                to_fparams(
                    {
                        date_field: dr,
                        "NgayTao": dr,
                        "KSKDK_NgayKham": dr,
                        "ChatLuongDuLieu": 4,
                        "page": 1,
                        "pageSize": 5000,
                    }
                ),
            )
            for r in ((d or {}).get("result") or {}).get("data") or []:
                index["no_cls_ids"].add(r.get("phieukhamId") or r.get("Id"))
        safe_print(f"  {mau} indexed phones={len(index['by_phone'])} names={len(index['by_name_year'])}", flush=True)
    return index


def match_patient(row: dict, index: dict) -> tuple[str, dict | None]:
    """Return (status, medinet_row)."""
    phone = re.sub(r"\D", "", str(row.get("sdt") or ""))
    name = (row.get("ho_ten") or "").strip().upper()
    year = str(row.get("nam_sinh") or "")
    sid = str(row.get("sid") or "")

    candidates = []
    if phone and phone in index["by_phone"]:
        candidates.extend(index["by_phone"][phone])
    key = f"{name}|{year}"
    if key in index["by_name_year"]:
        candidates.extend(index["by_name_year"][key])
    # SID sometimes aligns with internal codes in MaPhieu suffix — soft match by name only already done

    # dedupe
    seen = set()
    uniq = []
    for c in candidates:
        pid = c.get("phieukhamId") or c.get("Id")
        if pid in seen:
            continue
        seen.add(pid)
        uniq.append(c)

    if not uniq:
        return "WAITING_ADMIN", None

    # Prefer matching mau
    mau = row.get("mau_kham")
    preferred = [c for c in uniq if c.get("_mau") == mau] or uniq
    rec = preferred[0]
    pid = rec.get("phieukhamId") or rec.get("Id")
    if pid not in index["no_cls_ids"]:
        return "SKIP_ALREADY_CLS", rec
    return "READY_IMPORT", rec


def write_preview_excel(rows: list[dict], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Preview_CLS"
    header = [
        "STT",
        "file_name",
        "sid",
        "ho_ten",
        "nam_sinh",
        "gioi_tinh",
        "sdt",
        "mau_kham",
        "ngay_co_kq",
        "status_medinet",
        "medinet_MaPhieu",
        "medinet_NgayKham",
        "medinet_phieukhamId",
        "medinet_cdId",
        "parse_ok",
    ]
    for lab in LAB_COLS:
        header += [f"{lab}_raw", f"{lab}_unit_raw", f"{lab}_web", f"{lab}_unit_web", f"{lab}_note"]

    head_fill = PatternFill("solid", fgColor="1F4E79")
    head_font = Font(color="FFFFFF", bold=True)
    for c, h in enumerate(header, 1):
        cell = ws.cell(1, c, h)
        cell.fill = head_fill
        cell.font = head_font
        cell.alignment = Alignment(wrap_text=True, horizontal="center")

    for i, row in enumerate(rows, 1):
        labs = row.get("labs") or {}
        vals = [
            i,
            row.get("file_name"),
            row.get("sid"),
            row.get("ho_ten"),
            row.get("nam_sinh"),
            row.get("gioi_tinh"),
            row.get("sdt"),
            row.get("mau_kham"),
            row.get("ngay_co_kq"),
            row.get("status_medinet"),
            row.get("medinet_MaPhieu"),
            row.get("medinet_NgayKham"),
            row.get("medinet_phieukhamId"),
            row.get("medinet_cdId"),
            "YES" if row.get("parse_ok") else "NO",
        ]
        for lab in LAB_COLS:
            item = labs.get(lab) or {}
            vals += [
                item.get("value_raw", ""),
                item.get("unit_raw", ""),
                item.get("value_web", ""),
                item.get("unit_web", ""),
                item.get("convert_note", ""),
            ]
        for c, v in enumerate(vals, 1):
            ws.cell(1 + i, c, v)

    ws2 = wb.create_sheet("Missing_or_Updated")
    h2 = ["STT", "file_name", "sid", "ho_ten", "nam_sinh", "sdt", "mau_kham", "status_medinet", "reason"]
    for c, h in enumerate(h2, 1):
        cell = ws2.cell(1, c, h)
        cell.fill = head_fill
        cell.font = head_font
    r = 2
    stt = 1
    for row in rows:
        st = row.get("status_medinet")
        if st in ("WAITING_ADMIN", "SKIP_ALREADY_CLS", "PARSE_ERROR"):
            reason = {
                "WAITING_ADMIN": "Chưa thấy TTHC trên Medinet",
                "SKIP_ALREADY_CLS": "Đã có CLS trên web — cần kiểm tra trước khi ghi đè",
                "PARSE_ERROR": "Không đọc được PDF đủ thông tin",
            }.get(st, st)
            for c, v in enumerate(
                [
                    stt,
                    row.get("file_name"),
                    row.get("sid"),
                    row.get("ho_ten"),
                    row.get("nam_sinh"),
                    row.get("sdt"),
                    row.get("mau_kham"),
                    st,
                    reason,
                ],
                1,
            ):
                ws2.cell(r, c, v)
            r += 1
            stt += 1

    wb.save(path)


def update_cases_csv(cases_path: Path, rows: list[dict]) -> None:
    if not cases_path.exists():
        return
    with cases_path.open(encoding="utf-8-sig", newline="") as f:
        existing = list(csv.DictReader(f))
    by_file = {}
    for r in rows:
        by_file[Path(r.get("source_file") or r.get("file_name") or "").name] = r
        by_file[r.get("file_name")] = r

    for e in existing:
        src = Path(e.get("source_file") or "").name
        hit = by_file.get(src)
        if not hit:
            continue
        e["status"] = hit.get("status_medinet") or e.get("status")
        e["ho_ten"] = e.get("ho_ten") or hit.get("ho_ten")
        e["notes"] = f"phase_b:{hit.get('status_medinet')}"
        e["last_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if hit.get("medinet_MaPhieu"):
            e["ma_phieu"] = hit["medinet_MaPhieu"]

    if existing:
        with cases_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(existing[0].keys()))
            w.writeheader()
            w.writerows(existing)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="Limit PDFs for test (0=all)")
    ap.add_argument("--skip-medinet", action="store_true", help="Only parse PDFs, no Medinet match")
    ap.add_argument("--inbox", default="", help="Override inbox folder")
    args = ap.parse_args()

    cfg = load_config()
    build = build_root(cfg)
    inbox = Path(args.inbox) if args.inbox else inbox_dir(cfg)
    safe_print(f"Inbox: {inbox}")
    safe_print(f"Build: {build}")

    pdfs = list_pdfs(inbox, args.limit or None)
    safe_print(f"PDF count: {len(pdfs)}", flush=True)
    if not pdfs:
        safe_print("No PDFs found.")
        return 1

    rows = []
    for i, p in enumerate(pdfs, 1):
        try:
            data = extract_pdf(p)
        except Exception as e:
            data = {
                "source_file": str(p),
                "file_name": p.name,
                "parse_ok": False,
                "labs": {},
                "status_medinet": "PARSE_ERROR",
                "notes": str(e),
            }
        if not data.get("parse_ok"):
            data["status_medinet"] = data.get("status_medinet") or "PARSE_ERROR"
        rows.append(data)
        if i % 50 == 0 or i == len(pdfs):
            safe_print(f"  parsed {i}/{len(pdfs)}", flush=True)

    index = None
    if not args.skip_medinet:
        import os

        user = os.environ.get("MEDINET_USER", "pkdkthuankieu")
        password = os.environ.get("MEDINET_PASS", "P@ssw0rd")
        safe_print("Auth Medinet + index July lists...", flush=True)
        token = authenticate(user, password)
        date_from = cfg.get("medinet", {}).get("date_from", "01/07/2026")
        date_to = cfg.get("medinet", {}).get("date_to", "31/07/2026")
        index = fetch_unit_index(token, date_from, date_to)
        for row in rows:
            if row.get("status_medinet") == "PARSE_ERROR":
                continue
            st, rec = match_patient(row, index)
            row["status_medinet"] = st
            if rec:
                row["medinet_MaPhieu"] = rec.get("MaPhieu")
                nk = rec.get("NgayKham") or ""
                row["medinet_NgayKham"] = str(nk).split("T")[0]
                row["medinet_phieukhamId"] = rec.get("phieukhamId") or rec.get("Id")
                row["medinet_cdId"] = rec.get("cdId") or ""
            else:
                row["medinet_MaPhieu"] = ""
                row["medinet_NgayKham"] = ""
                row["medinet_phieukhamId"] = ""
                row["medinet_cdId"] = ""
    else:
        for row in rows:
            row.setdefault("status_medinet", "NOT_CHECKED")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = build / "excel_preview" / f"CLS_preview_{stamp}.xlsx"
    write_preview_excel(rows, out)
    # also copy missing sheet-only workbook
    missing_rows = [r for r in rows if r.get("status_medinet") in ("WAITING_ADMIN", "SKIP_ALREADY_CLS", "PARSE_ERROR")]
    miss_path = build / "missing_or_updated" / f"missing_or_updated_{stamp}.xlsx"
    write_preview_excel(missing_rows, miss_path)

    cases_path = ROOT / cfg.get("tracking", {}).get("cases_csv", "tracking/cases.csv")
    update_cases_csv(cases_path, rows)

    # summary
    from collections import Counter

    c = Counter(r.get("status_medinet") for r in rows)
    safe_print("---")
    safe_print(f"Preview Excel: {out}")
    safe_print(f"Missing/Updated Excel: {miss_path}")
    safe_print(f"Status: {dict(c)}")
    safe_print("NEXT: open Preview Excel, check value_web/unit_web. Then run import step.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
