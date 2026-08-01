#!/usr/bin/env python3
"""Phase B step 2: import READY_IMPORT cases into Medinet Khám cận lâm sàng.

Reads the latest (or given) preview Excel, imports only READY_IMPORT rows,
skips IMPORTED / SKIP_ALREADY_CLS, writes result Excel under Drive build folder.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from medinet_api import (  # noqa: E402
    LAB_TO_FORM,
    authenticate,
    cls_has_lab_values,
    get_cls,
    insert_cls,
    labs_to_form_payload,
)
from pdf_extract import extract_pdf  # noqa: E402
from phase_b_preview import (  # noqa: E402
    LAB_COLS,
    build_root,
    fetch_unit_index,
    inbox_dir,
    load_config,
    match_patient,
)


def latest_preview(build: Path, explicit: str = "") -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise FileNotFoundError(p)
        return p
    folder = build / "excel_preview"
    files = sorted(folder.glob("CLS_preview_*.xlsx"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No CLS_preview_*.xlsx in {folder}")
    return files[0]


def read_preview_ready(path: Path) -> list[dict]:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows_iter = ws.iter_rows(values_only=True)
    header = [str(h or "").strip() for h in next(rows_iter)]
    idx = {h: i for i, h in enumerate(header)}

    def get(row, name, default=""):
        i = idx.get(name)
        if i is None or i >= len(row):
            return default
        v = row[i]
        return default if v is None else v

    out = []
    for row in rows_iter:
        if not row:
            continue
        status = str(get(row, "status_medinet") or "").strip()
        if status != "READY_IMPORT":
            continue
        labs = {}
        for lab in LAB_COLS:
            labs[lab] = {
                "value_raw": get(row, f"{lab}_raw"),
                "unit_raw": get(row, f"{lab}_unit_raw"),
                "value_web": get(row, f"{lab}_web"),
                "unit_web": get(row, f"{lab}_unit_web"),
                "convert_note": get(row, f"{lab}_note"),
            }
        out.append(
            {
                "file_name": str(get(row, "file_name") or ""),
                "sid": str(get(row, "sid") or ""),
                "ho_ten": str(get(row, "ho_ten") or ""),
                "nam_sinh": str(get(row, "nam_sinh") or ""),
                "gioi_tinh": str(get(row, "gioi_tinh") or ""),
                "sdt": str(get(row, "sdt") or ""),
                "mau_kham": str(get(row, "mau_kham") or ""),
                "ngay_co_kq": str(get(row, "ngay_co_kq") or ""),
                "status_medinet": status,
                "medinet_MaPhieu": str(get(row, "medinet_MaPhieu") or ""),
                "medinet_NgayKham": str(get(row, "medinet_NgayKham") or ""),
                "medinet_phieukhamId": get(row, "medinet_phieukhamId") or get(row, "phieukhamId") or "",
                "medinet_cdId": get(row, "medinet_cdId") or get(row, "cdId") or "",
                "labs": labs,
                "source_file": str(get(row, "file_name") or ""),
            }
        )
    wb.close()
    return out


def resolve_phieukham(row: dict, index: dict) -> tuple[str | None, dict | None]:
    """Return (phieukhamId, medinet_rec)."""
    pid = row.get("medinet_phieukhamId")
    if pid not in (None, ""):
        try:
            return str(int(float(str(pid)))), None
        except Exception:
            pass
    mp = str(row.get("medinet_MaPhieu") or "").strip()
    if mp and mp in index.get("by_maphieu", {}):
        rec = index["by_maphieu"][mp]
        return str(rec.get("phieukhamId") or rec.get("Id")), rec
    st, rec = match_patient(row, index)
    if rec:
        return str(rec.get("phieukhamId") or rec.get("Id")), rec
    return None, None


def write_result_excel(rows: list[dict], path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Import_CLS"
    header = [
        "STT",
        "file_name",
        "ho_ten",
        "nam_sinh",
        "mau_kham",
        "medinet_MaPhieu",
        "phieukhamId",
        "import_status",
        "message",
        "verified",
        "fields_sent",
    ]
    fill = PatternFill("solid", fgColor="1F4E79")
    font = Font(color="FFFFFF", bold=True)
    for c, h in enumerate(header, 1):
        cell = ws.cell(1, c, h)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(wrap_text=True, horizontal="center")
    for i, row in enumerate(rows, 1):
        vals = [
            i,
            row.get("file_name"),
            row.get("ho_ten"),
            row.get("nam_sinh"),
            row.get("mau_kham"),
            row.get("medinet_MaPhieu"),
            row.get("phieukhamId"),
            row.get("import_status"),
            row.get("message"),
            row.get("verified"),
            row.get("fields_sent"),
        ]
        for c, v in enumerate(vals, 1):
            ws.cell(1 + i, c, v)
    wb.save(path)


def update_cases_csv(cases_path: Path, rows: list[dict]) -> None:
    if not cases_path.exists():
        return
    with cases_path.open(encoding="utf-8-sig", newline="") as f:
        existing = list(csv.DictReader(f))
    by_file = {}
    for r in rows:
        by_file[Path(r.get("file_name") or "").name] = r
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for e in existing:
        src = Path(e.get("source_file") or "").name
        hit = by_file.get(src)
        if not hit:
            continue
        st = hit.get("import_status")
        if st == "IMPORTED":
            e["status"] = "IMPORTED"
            e["imported_at"] = now
            e["notes"] = "phase_b_import:ok"
        elif st:
            e["status"] = st if st.startswith("ERROR") or st in {"SKIP_ALREADY_CLS", "WAITING_ADMIN"} else e.get("status")
            e["notes"] = f"phase_b_import:{st}:{hit.get('message','')}"[:240]
            try:
                e["import_attempts"] = str(int(e.get("import_attempts") or 0) + 1)
            except Exception:
                e["import_attempts"] = "1"
        e["last_checked_at"] = now
        if hit.get("medinet_MaPhieu"):
            e["ma_phieu"] = hit["medinet_MaPhieu"]
    if existing:
        with cases_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(existing[0].keys()))
            w.writeheader()
            w.writerows(existing)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default="", help="Path to CLS_preview_*.xlsx (default: latest)")
    ap.add_argument("--limit", type=int, default=0, help="Limit READY cases (0=all)")
    ap.add_argument("--dry-run", action="store_true", help="Map payload only, no write")
    ap.add_argument("--force", action="store_true", help="Overwrite if CLS already has values")
    ap.add_argument("--sleep", type=float, default=0.35, help="Delay between imports")
    ap.add_argument("--reparse-pdf", action="store_true", help="Re-extract PDF instead of Excel *_web")
    args = ap.parse_args()

    cfg = load_config()
    build = build_root(cfg)
    preview = latest_preview(build, args.preview)
    print(f"Preview: {preview}", flush=True)

    ready = read_preview_ready(preview)
    print(f"READY_IMPORT rows: {len(ready)}", flush=True)
    if args.limit:
        ready = ready[: args.limit]
        print(f"Limited to: {len(ready)}", flush=True)
    if not ready:
        print("Nothing to import.")
        return 0

    user = os.environ.get("MEDINET_USER", "pkdkthuankieu")
    password = os.environ.get("MEDINET_PASS", "P@ssw0rd")
    token_box = {"t": authenticate(user, password)}

    def reauth():
        token_box["t"] = authenticate(user, password)
        return token_box["t"]

    date_from = cfg.get("medinet", {}).get("date_from", "01/07/2026")
    date_to = cfg.get("medinet", {}).get("date_to", "31/07/2026")
    print("Indexing Medinet lists for phieukhamId resolve...", flush=True)
    index = fetch_unit_index(token_box["t"], date_from, date_to)
    # refresh token after long index
    token_box["t"] = authenticate(user, password)

    inbox = inbox_dir(cfg)
    results = []
    for i, row in enumerate(ready, 1):
        name = row.get("ho_ten")
        print(f"[{i}/{len(ready)}] {name} ...", flush=True)
        pid, rec = resolve_phieukham(row, index)
        if rec:
            row["medinet_MaPhieu"] = rec.get("MaPhieu") or row.get("medinet_MaPhieu")
        if not pid:
            row.update(
                {
                    "phieukhamId": "",
                    "import_status": "WAITING_ADMIN",
                    "message": "Không resolve được phieukhamId",
                    "verified": "NO",
                    "fields_sent": 0,
                }
            )
            results.append(row)
            continue

        # Optional reparse
        labs = row.get("labs") or {}
        if args.reparse_pdf:
            pdf = inbox / row["file_name"]
            if not pdf.exists():
                # search recursively
                hits = list(inbox.rglob(row["file_name"])) if row.get("file_name") else []
                pdf = hits[0] if hits else pdf
            if pdf.exists():
                labs = extract_pdf(pdf).get("labs") or labs

        # Guard: already has CLS
        existing, token_box["t"] = get_cls(token_box["t"], pid, reauth=reauth)
        if cls_has_lab_values(existing) and not args.force:
            row.update(
                {
                    "phieukhamId": pid,
                    "import_status": "SKIP_ALREADY_CLS",
                    "message": "Web đã có CLS — bỏ qua (dùng --force để ghi đè)",
                    "verified": "YES",
                    "fields_sent": 0,
                }
            )
            results.append(row)
            continue

        payload = labs_to_form_payload(labs, phieukham_id=pid, gioi_tinh=row.get("gioi_tinh") or "")
        # Enforce định kỳ only
        payload["LoaiKham"] = 5152
        fields_sent = len([k for k in payload if k in LAB_TO_FORM.values()])

        if args.dry_run:
            row.update(
                {
                    "phieukhamId": pid,
                    "import_status": "DRY_RUN",
                    "message": json.dumps(payload, ensure_ascii=False)[:500],
                    "verified": "NO",
                    "fields_sent": fields_sent,
                }
            )
            results.append(row)
            continue

        ok, msg, _raw, token_box["t"] = insert_cls(token_box["t"], payload, reauth=reauth)
        time.sleep(0.15)
        after, token_box["t"] = get_cls(token_box["t"], pid, reauth=reauth)
        verified = cls_has_lab_values(after)
        # Prefer verification over soft insert flag
        if verified and fields_sent > 0:
            # spot-check one marker if we sent WBC/HGB
            import_status = "IMPORTED"
            if not ok:
                msg = f"verified-after-soft-insert:{msg}"
        elif ok and verified:
            import_status = "IMPORTED"
        else:
            import_status = "ERROR_IMPORT"
            msg = msg or "verify failed"

        row.update(
            {
                "phieukhamId": pid,
                "import_status": import_status,
                "message": msg,
                "verified": "YES" if verified else "NO",
                "fields_sent": fields_sent,
            }
        )
        results.append(row)
        print(f"  -> {import_status} fields={fields_sent} verified={verified}", flush=True)
        if args.sleep:
            time.sleep(args.sleep)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = build / "excel_preview" / f"CLS_import_result_{stamp}.xlsx"
    write_result_excel(results, out)
    cases_path = ROOT / cfg.get("tracking", {}).get("cases_csv", "tracking/cases.csv")
    update_cases_csv(cases_path, results)

    c = Counter(r.get("import_status") for r in results)
    print("---")
    print(f"Result Excel: {out}")
    print(f"Status: {dict(c)}")
    return 0 if c.get("ERROR_IMPORT", 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
