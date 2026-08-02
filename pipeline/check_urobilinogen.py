#!/usr/bin/env python3
"""Check Urobilinogen: PDF has value vs web form.

Usage (Windows):
  cd C:\\Users\\thais\\ADMIN
  python .\\pipeline\\check_urobilinogen.py
  python .\\pipeline\\check_urobilinogen.py --folder PROCESSED
  python .\\pipeline\\check_urobilinogen.py --folder ALL
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from medinet_api import (  # noqa: E402
    authenticate,
    get_cls,
    labs_to_form_payload,
)
from pdf_extract import extract_pdf  # noqa: E402
from phase_b_preview import build_root, fetch_unit_index, load_config, match_patient  # noqa: E402
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()


def _folders(cfg: dict, which: str) -> list[Path]:
    sync = Path(cfg.get("drive", {}).get("local_sync_root") or "")
    if not sync.exists():
        sync = ROOT
    mapping = {
        "PROCESSED": sync / cfg["drive"].get("processed_folder", "PROCESSED"),
        "ERROR": sync / cfg["drive"].get("error_folder", "ERROR"),
        "INBOX": sync / cfg["drive"].get("inbox_folder", "INBOX_CLS"),
    }
    if which.upper() == "ALL":
        return [mapping["PROCESSED"], mapping["ERROR"], mapping["INBOX"]]
    key = which.upper()
    if key == "INBOX_CLS":
        key = "INBOX"
    return [mapping.get(key, mapping["PROCESSED"])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--folder",
        default="PROCESSED",
        help="PROCESSED | ERROR | INBOX | ALL",
    )
    ap.add_argument("--limit", type=int, default=0, help="Max PDFs to check (0=all)")
    args = ap.parse_args()

    cfg = load_config()
    dirs = _folders(cfg, args.folder)
    pdfs: list[Path] = []
    for d in dirs:
        if d.exists():
            pdfs.extend(sorted(d.rglob("*.pdf")))
    if args.limit:
        pdfs = pdfs[: args.limit]

    safe_print(f"Folders: {', '.join(str(d) for d in dirs)}")
    safe_print(f"PDF count: {len(pdfs)}")

    user = os.environ.get("MEDINET_USER", "pkdkthuankieu")
    password = os.environ.get("MEDINET_PASS", "P@ssw0rd")
    token = authenticate(user, password)
    date_from = cfg.get("medinet", {}).get("date_from", "01/07/2026")
    date_to = cfg.get("medinet", {}).get("date_to") or ""
    if not date_to:
        from datetime import date

        date_to = date.today().strftime("%d/%m/%Y")
    safe_print(f"Indexing Medinet {date_from} -> {date_to} ...")
    index = fetch_unit_index(token, date_from, date_to)
    token = authenticate(user, password)

    pdf_has = 0
    pdf_no = 0
    web_ok = 0
    web_missing = 0
    no_match = 0
    missing_rows: list[str] = []

    for i, pdf in enumerate(pdfs, 1):
        try:
            data = extract_pdf(pdf)
        except Exception as e:
            safe_print(f"[{i}] PARSE_FAIL {pdf.name}: {e}")
            continue
        labs = data.get("labs") or {}
        uro = labs.get("Urobilinogen") or {}
        uro_val = uro.get("value_web") or uro.get("value_raw") or ""
        if uro_val in (None, ""):
            pdf_no += 1
            continue
        pdf_has += 1

        st, rec = match_patient(data, index)
        pid = (rec or {}).get("phieukhamId") or (rec or {}).get("Id")
        if not pid:
            no_match += 1
            missing_rows.append(f"NO_TTHC\t{data.get('ho_ten')}\t{pdf.name}\tPDF={uro_val}")
            continue

        row, token = get_cls(token, pid)
        got = (row or {}).get("NuocTieu_Urobilinogen")
        payload = labs_to_form_payload(labs, phieukham_id=pid, gioi_tinh=data.get("gioi_tinh") or "")
        sent = payload.get("NuocTieu_Urobilinogen")

        if got in (None, ""):
            web_missing += 1
            missing_rows.append(
                f"WEB_MISSING\t{data.get('ho_ten')}\tpid={pid}\tPDF={uro_val}\tsent={sent}\t{pdf.name}"
            )
            safe_print(f"[{i}] THIEU web: {data.get('ho_ten')} pid={pid} PDF={uro_val}")
        else:
            web_ok += 1

    safe_print("")
    safe_print("========== TOM TAT UROBILINOGEN ==========")
    safe_print(f"PDF co Urobilinogen     : {pdf_has}")
    safe_print(f"PDF khong co            : {pdf_no}")
    safe_print(f"Web DA co (OK)          : {web_ok}")
    safe_print(f"Web THIEU (can repair)  : {web_missing}")
    safe_print(f"Chua khop TTHC          : {no_match}")
    safe_print("Import sau nay: neu PDF co Urobilinogen -> se gui NuocTieu_Urobilinogen.")
    safe_print("(Ure thuong khong co tren PDF -> web trong la binh thuong)")

    build = build_root(cfg)
    out = build / "excel_preview" / "urobilinogen_missing.txt"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(missing_rows) + ("\n" if missing_rows else ""), encoding="utf-8")
        safe_print(f"Chi tiet thieu: {out}")
    except Exception as e:
        safe_print(f"WARN khong ghi file: {e}")
        for line in missing_rows[:50]:
            safe_print(line)
    return 0 if web_missing == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
