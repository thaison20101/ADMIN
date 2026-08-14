#!/usr/bin/env python3
"""Full audit: missing Urobilinogen + has TTHC but not imported.

  python .\\pipeline\\rasoat_toan_bo.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from medinet_api import (  # noqa: E402
    authenticate,
    cls_has_lab_values,
    labs_to_form_payload,
    load_cls_view,
)
from pdf_extract import extract_pdf  # noqa: E402
from phase_b_preview import build_root, fetch_unit_index, load_config, match_patient  # noqa: E402
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()


def main() -> int:
    cfg = load_config()
    sync = Path(cfg.get("drive", {}).get("local_sync_root") or "")
    folders = {
        "PROCESSED": sync / cfg["drive"].get("processed_folder", "PROCESSED"),
        "ERROR": sync / cfg["drive"].get("error_folder", "ERROR"),
        "INBOX": sync / cfg["drive"].get("inbox_folder", "INBOX_CLS"),
    }
    pdfs: list[tuple[str, Path]] = []
    for label, d in folders.items():
        if not d.exists():
            safe_print(f"WARN missing folder: {d}")
            continue
        for p in sorted(d.rglob("*.pdf")):
            pdfs.append((label, p))
    safe_print(f"Tong PDF: {len(pdfs)}")

    from medinet_creds import get_medinet_creds

    user, password = get_medinet_creds(cfg)
    token = authenticate(user, password)
    date_from = cfg.get("medinet", {}).get("date_from", "01/07/2026")
    date_to = cfg.get("medinet", {}).get("date_to") or date.today().strftime("%d/%m/%Y")
    safe_print(f"Indexing Medinet {date_from} -> {date_to} ...")
    index = fetch_unit_index(token, date_from, date_to)
    token = authenticate(user, password)

    stats = Counter()
    uro_missing: list[str] = []
    tthc_chua_import: list[str] = []

    for i, (folder, pdf) in enumerate(pdfs, 1):
        try:
            data = extract_pdf(pdf)
        except Exception as e:
            stats["parse_fail"] += 1
            continue
        if not data.get("parse_ok"):
            stats["parse_fail"] += 1
            continue

        data["file_name"] = pdf.name
        data["source_file"] = str(pdf)
        st, rec = match_patient(data, index)
        pid = (rec or {}).get("phieukhamId") or (rec or {}).get("Id")

        labs = data.get("labs") or {}
        uro = labs.get("Urobilinogen") or {}
        uro_web = uro.get("value_web") or uro.get("value_raw") or ""
        payload = labs_to_form_payload(labs, phieukham_id=pid or 0, gioi_tinh=data.get("gioi_tinh") or "")
        sent_uro = payload.get("NuocTieu_Urobilinogen")

        if st == "WAITING_ADMIN" or not pid:
            stats["chua_co_tthc"] += 1
            continue

        stats["co_tthc"] += 1
        row, token = load_cls_view(token, pid)
        has_cls = cls_has_lab_values(row)
        got_uro = (row or {}).get("NuocTieu_Urobilinogen")

        # A) Has TTHC but CLS empty / not imported
        if not has_cls:
            stats["tthc_chua_import_cls"] += 1
            tthc_chua_import.append(
                f"CHUA_IMPORT_CLS\t{folder}\t{data.get('ho_ten')}\tpid={pid}\tmatch={st}\t{pdf.name}"
            )
            if i % 50 == 0:
                safe_print(f"[{i}] scan...")
            continue

        stats["da_co_cls"] += 1

        # B) PDF has urobilinogen but web missing / wrong tiny value
        if sent_uro not in (None, ""):
            stats["pdf_co_uro"] += 1
            need = got_uro in (None, "")
            if not need and got_uro not in (None, ""):
                try:
                    g = float(str(got_uro).replace(",", "."))
                    s = float(str(sent_uro).replace(",", "."))
                    if g < 1.5 and s >= 1.5:
                        need = True
                except Exception:
                    pass
            if need:
                stats["web_thieu_uro"] += 1
                uro_missing.append(
                    f"WEB_THIEU_URO\t{folder}\t{data.get('ho_ten')}\tpid={pid}\t"
                    f"PDF={uro_web}\tsent={sent_uro}\tweb={got_uro}\t{pdf.name}"
                )
                safe_print(
                    f"[{i}] THIEU URO {data.get('ho_ten')} pid={pid} folder={folder} sent={sent_uro}"
                )
            else:
                stats["web_uro_ok"] += 1
        else:
            stats["pdf_khong_uro"] += 1

    build = build_root(cfg)
    out_dir = build / "excel_preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    f_uro = out_dir / "rasoat_thieu_urobilinogen.txt"
    f_imp = out_dir / "rasoat_tthc_chua_import.txt"
    f_uro.write_text("\n".join(uro_missing) + ("\n" if uro_missing else ""), encoding="utf-8")
    f_imp.write_text("\n".join(tthc_chua_import) + ("\n" if tthc_chua_import else ""), encoding="utf-8")

    safe_print("")
    safe_print("========== RASOAT TOAN BO ==========")
    safe_print(f"Tong PDF                 : {len(pdfs)}")
    safe_print(f"Parse fail               : {stats['parse_fail']}")
    safe_print(f"Chua co TTHC             : {stats['chua_co_tthc']}")
    safe_print(f"Co TTHC                  : {stats['co_tthc']}")
    safe_print(f"  - Chua import CLS      : {stats['tthc_chua_import_cls']}  -> can import")
    safe_print(f"  - Da co CLS tren web   : {stats['da_co_cls']}")
    safe_print(f"PDF co Urobilinogen      : {stats['pdf_co_uro']}")
    safe_print(f"PDF khong co Uro         : {stats['pdf_khong_uro']}")
    safe_print(f"Web Uro OK               : {stats['web_uro_ok']}")
    safe_print(f"Web THIEU Uro (repair)   : {stats['web_thieu_uro']}")
    safe_print(f"List thieu uro           : {f_uro}")
    safe_print(f"List TTHC chua import    : {f_imp}")
    safe_print("====================================")

    # Non-zero if work remains
    if stats["tthc_chua_import_cls"] or stats["web_thieu_uro"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
