#!/usr/bin/env python3
"""One automated cycle: inbox PDFs → match Medinet → import CLS for READY cases.

Used by hourly_sync. Safe to re-run: skips IMPORTED / SKIP_ALREADY_CLS.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from medinet_api import (  # noqa: E402
    LAB_TO_FORM,
    authenticate,
    cls_has_lab_values,
    get_cls,
    insert_cls,
    labs_to_form_payload,
    verify_cls_saved,
)
from pdf_extract import extract_pdf  # noqa: E402
from phase_b_import import write_result_excel  # noqa: E402
from phase_b_preview import (  # noqa: E402
    build_root,
    fetch_unit_index,
    load_config,
    match_patient,
)
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()

PENDING = {"NEW_LAB", "WAITING_ADMIN", "READY_IMPORT", "ERROR", "ERROR_IMPORT"}
TERMINAL_SKIP = {"IMPORTED", "SKIP_ALREADY_CLS", "PARSE_ERROR"}


def _today_dmy() -> str:
    return date.today().strftime("%d/%m/%Y")


def _resolve_pdf(row: dict, inbox: Path) -> Path | None:
    src = Path(row.get("source_file") or "")
    if src.exists():
        return src
    name = src.name or row.get("file_name") or ""
    if not name:
        return None
    hits = list(inbox.rglob(name))
    return hits[0] if hits else None


def run_auto_cycle(
    *,
    dry_run: bool = False,
    limit: int = 0,
    force: bool = False,
    sleep_s: float = 0.25,
) -> dict:
    """Process pending inbox cases. Returns stats dict."""
    cfg = load_config()
    build = build_root(cfg)
    sync = Path(cfg.get("drive", {}).get("local_sync_root") or "")
    inbox = sync / cfg["drive"]["inbox_folder"] if sync.exists() else ROOT / "INBOX_CLS"
    processed = sync / cfg["drive"]["processed_folder"] if sync.exists() else ROOT / "PROCESSED"
    error_dir = sync / cfg["drive"]["error_folder"] if sync.exists() else ROOT / "ERROR"
    for p in (inbox, processed, error_dir):
        p.mkdir(parents=True, exist_ok=True)

    cases_path = ROOT / cfg.get("tracking", {}).get("cases_csv", "tracking/cases.csv")
    from hourly_sync import read_cases, register_new_files, write_cases  # local import

    rows = read_cases(cases_path)
    added = register_new_files(inbox, rows)
    safe_print(f"Inbox: {inbox}")
    safe_print(f"New files registered: {added}")

    max_per_run = int(cfg.get("import_rules", {}).get("max_imports_per_run", 80))
    if limit:
        max_per_run = min(max_per_run, limit)

    user = os.environ.get("MEDINET_USER", "pkdkthuankieu")
    password = os.environ.get("MEDINET_PASS", "P@ssw0rd")
    token_box = {"t": authenticate(user, password)}

    def reauth():
        token_box["t"] = authenticate(user, password)
        return token_box["t"]

    date_from = cfg.get("medinet", {}).get("date_from", "01/07/2026")
    date_to = cfg.get("medinet", {}).get("date_to") or _today_dmy()
    # If configured end date is in the past relative to "rolling", extend to today
    safe_print(f"Indexing Medinet {date_from} -> {date_to} ...")
    index = fetch_unit_index(token_box["t"], date_from, date_to)
    token_box["t"] = authenticate(user, password)

    stats = Counter()
    results = []
    imported_n = 0

    for row in rows:
        status = (row.get("status") or "").upper()
        if status in {"IMPORTED"}:
            stats["skipped_imported"] += 1
            continue
        if status not in PENDING and status != "SKIP_ALREADY_CLS":
            # still allow recheck unknown
            if status not in {"NEW_LAB", "WAITING_ADMIN", "READY_IMPORT", "ERROR", "ERROR_IMPORT"}:
                continue

        pdf = _resolve_pdf(row, inbox)
        if not pdf or not pdf.exists():
            row["notes"] = "source_pdf_missing"
            stats["missing_pdf"] += 1
            continue

        try:
            data = extract_pdf(pdf)
        except Exception as e:
            row["status"] = "PARSE_ERROR"
            row["notes"] = f"parse:{e}"[:200]
            stats["parse_error"] += 1
            continue

        if not data.get("parse_ok"):
            row["status"] = "PARSE_ERROR"
            row["ho_ten"] = row.get("ho_ten") or data.get("ho_ten") or ""
            row["notes"] = "parse_ok=false"
            stats["parse_error"] += 1
            continue

        row["ho_ten"] = data.get("ho_ten") or row.get("ho_ten") or ""
        row["mau_kham"] = data.get("mau_kham") or row.get("mau_kham") or ""
        st, rec = match_patient(data, index)
        row["last_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if st == "WAITING_ADMIN":
            row["status"] = "WAITING_ADMIN"
            row["has_admin_info"] = "NO"
            row["notes"] = "no_tthc_match"
            stats["waiting_admin"] += 1
            continue

        # IMPORTANT: UI opens by phieukhamId — never use cdId as save key
        pid = rec.get("phieukhamId") if rec else None
        if pid in (None, ""):
            pid = rec.get("Id") if rec else None
        cdid = rec.get("cdId") if rec else None
        # Guard: cdId must not be mistaken for phieukhamId
        if rec and cdid not in (None, "") and pid not in (None, "") and int(pid) == int(cdid):
            # extremely rare; keep phieukhamId field explicitly
            pid = rec.get("phieukhamId") or pid
        pid = str(pid or "")
        if rec:
            row["ma_phieu"] = rec.get("MaPhieu") or row.get("ma_phieu") or ""
            row["has_admin_info"] = "YES"

        if st == "SKIP_ALREADY_CLS":
            # Double-check via Get — list quality filter can lag
            existing, token_box["t"] = get_cls(token_box["t"], pid, reauth=reauth) if pid else (None, token_box["t"])
            if cls_has_lab_values(existing) and not force:
                row["status"] = "SKIP_ALREADY_CLS"
                row["notes"] = "already_has_cls"
                stats["skip_already_cls"] += 1
                continue
            # list said has CLS but Get empty → treat as ready
            st = "READY_IMPORT"

        if not pid:
            row["status"] = "WAITING_ADMIN"
            row["notes"] = "missing_phieukhamId"
            stats["waiting_admin"] += 1
            continue

        existing, token_box["t"] = get_cls(token_box["t"], pid, reauth=reauth)
        if cls_has_lab_values(existing) and not force:
            row["status"] = "SKIP_ALREADY_CLS"
            row["notes"] = "already_has_cls_get"
            stats["skip_already_cls"] += 1
            continue

        if imported_n >= max_per_run:
            row["status"] = "READY_IMPORT"
            row["notes"] = "queued_max_per_run"
            stats["queued"] += 1
            continue

        payload = labs_to_form_payload(
            data.get("labs") or {},
            phieukham_id=pid,
            gioi_tinh=data.get("gioi_tinh") or "",
        )
        payload["LoaiKham"] = 5152
        if cdid not in (None, ""):
            payload["cdId"] = int(cdid)
        fields_sent = len([k for k in payload if k in LAB_TO_FORM.values()])

        result_row = {
            "file_name": pdf.name,
            "ho_ten": data.get("ho_ten"),
            "nam_sinh": data.get("nam_sinh"),
            "mau_kham": data.get("mau_kham"),
            "medinet_MaPhieu": row.get("ma_phieu"),
            "phieukhamId": pid,
            "cdId": cdid or "",
            "fields_sent": fields_sent,
        }

        if dry_run:
            row["status"] = "READY_IMPORT"
            row["notes"] = "dry_run"
            result_row.update({"import_status": "DRY_RUN", "message": "dry_run", "verified": "NO"})
            results.append(result_row)
            stats["dry_run"] += 1
            continue

        ok, msg, _raw, token_box["t"] = insert_cls(token_box["t"], payload, reauth=reauth)
        time.sleep(0.15)
        verified, vdetail, token_box["t"] = verify_cls_saved(
            token_box["t"], pid, payload=payload, reauth=reauth
        )
        attempts = int(row.get("import_attempts") or 0) + 1
        row["import_attempts"] = str(attempts)
        msg = f"{msg}; {vdetail}"

        if ok and verified and fields_sent > 0:
            row["status"] = "IMPORTED"
            row["imported_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row["notes"] = msg or "imported"
            result_row.update({"import_status": "IMPORTED", "message": msg, "verified": "YES"})
            stats["imported"] += 1
            imported_n += 1
            try:
                under_inbox = inbox.resolve() in pdf.resolve().parents or pdf.parent.resolve() == inbox.resolve()
            except Exception:
                under_inbox = str(inbox) in str(pdf)
            if pdf.exists() and under_inbox:
                try:
                    dest = processed / pdf.name
                    if dest.exists():
                        dest = processed / f"{pdf.stem}_{pid}{pdf.suffix}"
                    shutil.move(str(pdf), str(dest))
                    row["source_file"] = str(dest)
                except Exception as e:
                    row["notes"] = f"imported_but_move_failed:{e}"[:200]
            safe_print(f"  IMPORTED {data.get('ho_ten')} pid={pid} fields={fields_sent}")
        else:
            max_attempts = int(cfg.get("tracking", {}).get("max_import_attempts", 5))
            row["status"] = "ERROR_IMPORT" if attempts >= max_attempts else "READY_IMPORT"
            row["notes"] = f"import_fail:{msg}"[:200]
            result_row.update(
                {
                    "import_status": "ERROR_IMPORT",
                    "message": msg,
                    "verified": "YES" if verified else "NO",
                }
            )
            stats["error_import"] += 1
            if row["status"] == "ERROR_IMPORT" and pdf.exists():
                try:
                    dest = error_dir / pdf.name
                    if dest.exists():
                        dest = error_dir / f"{pdf.stem}_{pid}{pdf.suffix}"
                    shutil.move(str(pdf), str(dest))
                    row["source_file"] = str(dest)
                except Exception:
                    pass
            safe_print(f"  ERROR {data.get('ho_ten')} pid={pid} msg={msg}")

        results.append(result_row)
        if sleep_s:
            time.sleep(sleep_s)

    write_cases(cases_path, rows)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if results:
        out = build / "excel_preview" / f"CLS_auto_import_{stamp}.xlsx"
        write_result_excel(results, out)
        safe_print(f"Result Excel: {out}")

    # snapshot ledger
    snap = build / "cases_snapshot" / f"cases-{stamp}.csv"
    try:
        shutil.copy2(cases_path, snap)
    except Exception:
        pass

    summary = dict(stats)
    summary["new_files"] = added
    summary["results"] = len(results)
    safe_print(f"Auto cycle stats: {summary}")
    return summary


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    run_auto_cycle(dry_run=args.dry_run, limit=args.limit, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
