#!/usr/bin/env python3
"""Repair missing Urobilinogen on web (convert mg/dL→µmol/L, re-import).

Prefer list from build/.../urobilinogen_missing.txt if present.

  cd C:\\Users\\thais\\ADMIN
  python .\\pipeline\\repair_urobilinogen.py
"""

from __future__ import annotations

import argparse
import os
import re
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
    load_cls_view,
    verify_cls_saved,
)
from pdf_extract import extract_pdf  # noqa: E402
from phase_b_preview import build_root, fetch_unit_index, load_config, match_patient  # noqa: E402
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()


def _load_targets_from_missing_txt(path: Path) -> list[tuple[str, str]]:
    """Return list of (pid, pdf_name) from urobilinogen_missing.txt."""
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("WEB_MISSING"):
            continue
        m_pid = re.search(r"pid=(\d+)", line)
        # filename is last token ending with .pdf
        m_pdf = re.search(r"(\S+\.pdf)\s*$", line, re.I)
        if m_pid and m_pdf:
            out.append((m_pid.group(1), m_pdf.group(1)))
    return out


def _find_pdf(name: str, roots: list[Path]) -> Path | None:
    for root in roots:
        if not root.exists():
            continue
        hits = list(root.rglob(name))
        if hits:
            return hits[0]
    return None


def main() -> int:
    cfg = load_config()
    sync = Path(cfg.get("drive", {}).get("local_sync_root") or "")
    processed = sync / cfg["drive"].get("processed_folder", "PROCESSED")
    error = sync / cfg["drive"].get("error_folder", "ERROR")
    inbox = sync / cfg["drive"].get("inbox_folder", "INBOX_CLS")
    roots = [processed, error, inbox]

    build = build_root(cfg)
    missing_txt = build / "excel_preview" / "urobilinogen_missing.txt"
    targets = _load_targets_from_missing_txt(missing_txt)
    safe_print(f"Missing list: {missing_txt} ({len(targets)} rows)")

    pdfs: list[tuple[Path, str | None]] = []
    if targets:
        for pid, name in targets:
            p = _find_pdf(name, roots)
            if p:
                pdfs.append((p, pid))
            else:
                safe_print(f"PDF not found: {name}")
    else:
        safe_print("No missing list — scan all PROCESSED/ERROR/INBOX")
        for d in roots:
            if d.exists():
                for p in sorted(d.rglob("*.pdf")):
                    pdfs.append((p, None))

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

    fixed = skipped_ok = failed = no_uro = no_match = 0

    for i, (pdf, pid_hint) in enumerate(pdfs, 1):
        try:
            data = extract_pdf(pdf)
        except Exception as e:
            safe_print(f"[{i}] PARSE {pdf.name}: {e}")
            failed += 1
            continue
        labs = data.get("labs") or {}
        uro = labs.get("Urobilinogen") or {}
        uro_web = uro.get("value_web") or ""
        if uro_web in (None, ""):
            no_uro += 1
            continue

        data["file_name"] = pdf.name
        st, rec = match_patient(data, index)
        pid = pid_hint or (rec or {}).get("phieukhamId") or (rec or {}).get("Id")
        if not pid and rec:
            pid = rec.get("phieukhamId") or rec.get("Id")
        if not pid:
            no_match += 1
            safe_print(f"[{i}] NO_MATCH {data.get('ho_ten')} {pdf.name}")
            continue

        row, token = load_cls_view(token, pid, reauth=reauth)
        got = (row or {}).get("NuocTieu_Urobilinogen")
        # Still repair if web empty OR web has raw 0.2 (sai đơn vị)
        need = False
        if got in (None, ""):
            need = True
        else:
            try:
                if float(str(got).replace(",", ".")) < 1.5 and float(str(uro_web).replace(",", ".")) >= 1.5:
                    need = True  # web còn 0.2, PDF đã convert
            except Exception:
                pass
        if not need:
            skipped_ok += 1
            continue

        payload = labs_to_form_payload(
            labs, phieukham_id=pid, gioi_tinh=data.get("gioi_tinh") or ""
        )
        payload["LoaiKham"] = 5152
        cdid = (rec or {}).get("cdId") if rec else None
        if cdid not in (None, ""):
            payload["cdId"] = int(cdid)

        sent = payload.get("NuocTieu_Urobilinogen")
        if sent in (None, ""):
            safe_print(f"[{i}] NO_PAYLOAD_URO {data.get('ho_ten')} raw={uro.get('value_raw')}")
            failed += 1
            continue

        safe_print(
            f"[{i}] REPAIR {data.get('ho_ten')} pid={pid} "
            f"raw={uro.get('value_raw')} {uro.get('unit_raw')} -> {sent} "
            f"| {uro.get('convert_note')}"
        )
        ok, msg, _raw, token = insert_cls(token, payload, reauth=reauth)
        time.sleep(0.15)
        verified, vdetail, token = verify_cls_saved(token, pid, payload=payload, reauth=reauth)
        row2, token = load_cls_view(token, pid, reauth=reauth)
        got2 = (row2 or {}).get("NuocTieu_Urobilinogen")
        if ok and got2 not in (None, ""):
            fixed += 1
            safe_print(f"    OK web_uro={got2}")
        else:
            failed += 1
            safe_print(f"    FAIL web_uro={got2} ok={ok} verified={verified} {msg}; {vdetail}")

    safe_print("")
    safe_print("========== REPAIR UROBILINOGEN ==========")
    safe_print(f"Da sua              : {fixed}")
    safe_print(f"Da dung (bo qua)    : {skipped_ok}")
    safe_print(f"That bai            : {failed}")
    safe_print(f"PDF khong co uro    : {no_uro}")
    safe_print(f"Khong khop TTHC     : {no_match}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
