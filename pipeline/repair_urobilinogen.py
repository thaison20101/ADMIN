#!/usr/bin/env python3
"""Repair missing Urobilinogen on web (convert mg/dL→µmol/L, re-import).

  cd C:\\Users\\thais\\ADMIN
  python .\\pipeline\\repair_urobilinogen.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from medinet_api import (  # noqa: E402
    authenticate,
    get_cls,
    insert_cls,
    labs_to_form_payload,
    verify_cls_saved,
)
from pdf_extract import extract_pdf, normalize_for_web  # noqa: E402
from phase_b_preview import fetch_unit_index, load_config, match_patient  # noqa: E402
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()


def main() -> int:
    cfg = load_config()
    sync = Path(cfg.get("drive", {}).get("local_sync_root") or "")
    processed = sync / cfg["drive"].get("processed_folder", "PROCESSED")
    error = sync / cfg["drive"].get("error_folder", "ERROR")
    inbox = sync / cfg["drive"].get("inbox_folder", "INBOX_CLS")
    pdfs = []
    for d in (processed, error, inbox):
        if d.exists():
            pdfs.extend(sorted(d.rglob("*.pdf")))

    user = os.environ.get("MEDINET_USER", "pkdkthuankieu")
    password = os.environ.get("MEDINET_PASS", "P@ssw0rd")
    token = authenticate(user, password)

    from datetime import date

    date_from = cfg.get("medinet", {}).get("date_from", "01/07/2026")
    date_to = cfg.get("medinet", {}).get("date_to") or date.today().strftime("%d/%m/%Y")
    safe_print(f"Indexing {date_from} -> {date_to} ...")
    index = fetch_unit_index(token, date_from, date_to)
    token = authenticate(user, password)

    def reauth():
        nonlocal token
        token = authenticate(user, password)
        return token

    fixed = 0
    skipped_ok = 0
    failed = 0
    no_uro = 0
    no_match = 0

    for i, pdf in enumerate(pdfs, 1):
        try:
            data = extract_pdf(pdf)
        except Exception as e:
            safe_print(f"[{i}] PARSE {pdf.name}: {e}")
            continue
        labs = data.get("labs") or {}
        uro = labs.get("Urobilinogen") or {}
        uro_web = uro.get("value_web") or ""
        if uro_web in (None, ""):
            no_uro += 1
            continue

        data["file_name"] = pdf.name
        st, rec = match_patient(data, index)
        pid = (rec or {}).get("phieukhamId") or (rec or {}).get("Id")
        if not pid:
            no_match += 1
            continue

        row, token = get_cls(token, pid, reauth=reauth)
        got = (row or {}).get("NuocTieu_Urobilinogen")
        if got not in (None, ""):
            skipped_ok += 1
            continue

        payload = labs_to_form_payload(
            labs, phieukham_id=pid, gioi_tinh=data.get("gioi_tinh") or ""
        )
        payload["LoaiKham"] = 5152
        cdid = (rec or {}).get("cdId")
        if cdid not in (None, ""):
            payload["cdId"] = int(cdid)

        if "NuocTieu_Urobilinogen" not in payload:
            safe_print(
                f"[{i}] SKIP no payload uro {data.get('ho_ten')} raw={uro.get('value_raw')} web={uro_web}"
            )
            failed += 1
            continue

        safe_print(
            f"[{i}] REPAIR {data.get('ho_ten')} pid={pid} "
            f"raw={uro.get('value_raw')} {uro.get('unit_raw')} -> web={payload.get('NuocTieu_Urobilinogen')} "
            f"({uro.get('convert_note')})"
        )
        ok, msg, _raw, token = insert_cls(token, payload, reauth=reauth)
        time.sleep(0.12)
        verified, vdetail, token = verify_cls_saved(token, pid, payload=payload, reauth=reauth)
        row2, token = get_cls(token, pid, reauth=reauth)
        got2 = (row2 or {}).get("NuocTieu_Urobilinogen")
        if ok and got2 not in (None, ""):
            fixed += 1
            safe_print(f"    OK uro={got2} ({msg}; {vdetail})")
        else:
            failed += 1
            safe_print(f"    FAIL got={got2} ok={ok} msg={msg}; {vdetail}")

    safe_print("")
    safe_print("========== REPAIR UROBILINOGEN ==========")
    safe_print(f"Da sua (web co uro) : {fixed}")
    safe_print(f"Da co san (bo qua)  : {skipped_ok}")
    safe_print(f"That bai            : {failed}")
    safe_print(f"PDF khong co uro    : {no_uro}")
    safe_print(f"Khong khop TTHC     : {no_match}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
