#!/usr/bin/env python3
"""Hourly pipeline skeleton for Drive inbox → admin check → import queue.

Flow:
1) Scan local Drive-synced INBOX_CLS for new files
2) Register new cases as NEW_LAB
3) For NEW_LAB / WAITING_ADMIN: check whether admin info exists (hook)
4) If admin exists -> READY_IMPORT (later: import to Medinet web)
5) Skip IMPORTED forever
6) Move files to PROCESSED / ERROR when terminal

Import-to-web rules are intentionally stubbed until you provide exact requirements.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "pipeline" / "config.example.json"
LOCAL_CONFIG = ROOT / "pipeline" / "config.local.json"
CASES_CSV = ROOT / "tracking" / "cases.csv"

STATUSES_SKIP = {"IMPORTED"}
STATUSES_RECHECK = {"NEW_LAB", "WAITING_ADMIN", "READY_IMPORT", "ERROR"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def load_config() -> dict:
    path = LOCAL_CONFIG if LOCAL_CONFIG.exists() else DEFAULT_CONFIG
    # utf-8-sig: tolerate Windows PowerShell Set-Content BOM
    with path.open(encoding="utf-8-sig") as f:
        cfg = json.load(f)
    cfg["_config_path"] = str(path)
    return cfg


def ensure_cases_csv(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "case_key",
                "source_file",
                "file_hash",
                "ho_ten",
                "cccd",
                "ngay_kham",
                "mau_kham",
                "ma_phieu",
                "has_lab_file",
                "has_admin_info",
                "status",
                "import_attempts",
                "last_checked_at",
                "imported_at",
                "notes",
            ]
        )


def read_cases(path: Path) -> list[dict]:
    ensure_cases_csv(path)
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_cases(path: Path, rows: list[dict]) -> None:
    ensure_cases_csv(path)
    fieldnames = [
        "case_key",
        "source_file",
        "file_hash",
        "ho_ten",
        "cccd",
        "ngay_kham",
        "mau_kham",
        "ma_phieu",
        "has_lab_file",
        "has_admin_info",
        "status",
        "import_attempts",
        "last_checked_at",
        "imported_at",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def sha256_file(path: Path, limit_mb: int = 64) -> str:
    h = hashlib.sha256()
    max_bytes = limit_mb * 1024 * 1024
    total = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
            if total >= max_bytes:
                break
    return h.hexdigest()


def parse_filename_hints(name: str) -> dict:
    """Best-effort parse from names like: 220726-464922 - HUYNH THI LE HANG - 1973 - F.pdf"""
    stem = Path(name).stem
    out = {"ho_ten": "", "cccd": "", "ngay_kham": "", "mau_kham": "", "ma_phieu": ""}
    parts = [p.strip() for p in re.split(r"\s+-\s+", stem)]
    if len(parts) >= 2:
        out["ho_ten"] = parts[1]
    # leading code may encode date + id
    if parts:
        m = re.match(r"(\d{6})-(\d+)", parts[0])
        if m:
            ddmmyy, seq = m.groups()
            dd, mm, yy = ddmmyy[:2], ddmmyy[2:4], ddmmyy[4:6]
            out["ngay_kham"] = f"20{yy}-{mm}-{dd}"
            out["ma_phieu"] = parts[0]
    # M2/M3/M4 marker if present
    m = re.search(r"\b(M1{0,2}|M2|M3|M4|M11|M12|M13)\b", stem, re.I)
    if m:
        out["mau_kham"] = m.group(1).upper()
    return out


def resolve_inbox_dirs(cfg: dict) -> tuple[Path, Path, Path]:
    sync_root = Path(cfg["drive"].get("local_sync_root") or "")
    if sync_root and sync_root.exists():
        inbox = sync_root / cfg["drive"]["inbox_folder"]
        processed = sync_root / cfg["drive"]["processed_folder"]
        error = sync_root / cfg["drive"]["error_folder"]
    else:
        # Fallback to repo-local folders (for dry-run / early setup)
        inbox = ROOT / "INBOX_CLS"
        processed = ROOT / "PROCESSED"
        error = ROOT / "ERROR"
    inbox.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    error.mkdir(parents=True, exist_ok=True)
    return inbox, processed, error


def check_admin_info(case: dict) -> tuple[bool | None, str]:
    """Hook: check Medinet whether administrative info exists.

    Returns (has_admin, note).
    Currently a stub — returns None meaning 'not checked / not configured'.
    """
    # Placeholder for future Medinet API/UI check using MEDINET_USER/MEDINET_PASS.
    _ = os.environ.get("MEDINET_USER"), os.environ.get("MEDINET_PASS")
    return None, "admin_check_not_configured_yet"


def import_lab_to_web(case: dict, source_file: Path) -> tuple[bool, str]:
    """Hook: import lab results to Medinet web.

    Stub until you provide exact import requirements.
    """
    _ = case, source_file
    return False, "import_rules_not_enabled"


def register_new_files(inbox: Path, rows: list[dict]) -> int:
    by_hash = {r.get("file_hash"): r for r in rows if r.get("file_hash")}
    by_key = {r.get("case_key"): r for r in rows if r.get("case_key")}
    added = 0
    for path in sorted(inbox.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".xls", ".csv"}:
            continue
        digest = sha256_file(path)
        if digest in by_hash:
            continue
        hints = parse_filename_hints(path.name)
        case_key = hints.get("ma_phieu") or digest[:16]
        if case_key in by_key:
            # same key different file — keep both via hash suffix
            case_key = f"{case_key}_{digest[:8]}"
        row = {
            "case_key": case_key,
            "source_file": str(path),
            "file_hash": digest,
            "ho_ten": hints.get("ho_ten", ""),
            "cccd": hints.get("cccd", ""),
            "ngay_kham": hints.get("ngay_kham", ""),
            "mau_kham": hints.get("mau_kham", ""),
            "ma_phieu": hints.get("ma_phieu", ""),
            "has_lab_file": "YES",
            "has_admin_info": "",
            "status": "NEW_LAB",
            "import_attempts": "0",
            "last_checked_at": now_iso(),
            "imported_at": "",
            "notes": "registered_from_inbox",
        }
        rows.append(row)
        by_hash[digest] = row
        by_key[case_key] = row
        added += 1
        print(f"+ NEW_LAB {case_key} <- {path.name}")
    return added


def process_pending(rows: list[dict], cfg: dict, processed: Path, error: Path, dry_run: bool) -> dict:
    stats = {"rechecked": 0, "waiting_admin": 0, "ready": 0, "imported": 0, "errors": 0, "skipped": 0}
    max_attempts = int(cfg.get("tracking", {}).get("max_import_attempts", 5))
    import_enabled = bool(cfg.get("import_rules", {}).get("enabled", False))

    for row in rows:
        status = (row.get("status") or "").upper()
        if status in STATUSES_SKIP:
            stats["skipped"] += 1
            continue
        if status not in STATUSES_RECHECK:
            continue

        stats["rechecked"] += 1
        row["last_checked_at"] = now_iso()

        has_admin, admin_note = check_admin_info(row)
        if has_admin is None:
            # Not configured yet: keep as WAITING_ADMIN after first sight
            if status == "NEW_LAB":
                row["status"] = "WAITING_ADMIN"
                row["notes"] = admin_note
                stats["waiting_admin"] += 1
            else:
                row["notes"] = admin_note
                stats["waiting_admin"] += 1
            continue

        row["has_admin_info"] = "YES" if has_admin else "NO"
        if not has_admin:
            row["status"] = "WAITING_ADMIN"
            row["notes"] = admin_note or "missing_admin_info"
            stats["waiting_admin"] += 1
            continue

        row["status"] = "READY_IMPORT"
        stats["ready"] += 1

        if not import_enabled:
            row["notes"] = "ready_but_import_rules_disabled"
            continue

        src = Path(row.get("source_file") or "")
        ok, msg = import_lab_to_web(row, src)
        attempts = int(row.get("import_attempts") or 0) + 1
        row["import_attempts"] = str(attempts)
        if ok:
            row["status"] = "IMPORTED"
            row["imported_at"] = now_iso()
            row["notes"] = msg
            stats["imported"] += 1
            if src.exists() and not dry_run:
                dest = processed / src.name
                shutil.move(str(src), str(dest))
                row["source_file"] = str(dest)
        else:
            if attempts >= max_attempts:
                row["status"] = "ERROR"
                row["notes"] = msg
                stats["errors"] += 1
                if src.exists() and not dry_run:
                    dest = error / src.name
                    shutil.move(str(src), str(dest))
                    row["source_file"] = str(dest)
            else:
                row["status"] = "READY_IMPORT"
                row["notes"] = f"retryable: {msg}"
    return stats


def summarize(rows: list[dict]) -> dict:
    c: dict[str, int] = {}
    for r in rows:
        s = r.get("status") or "?"
        c[s] = c.get(s, 0) + 1
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description="Hourly Drive→Medinet pipeline skeleton")
    ap.add_argument("--dry-run", action="store_true", help="Do not move files")
    ap.add_argument("--cases", default=str(CASES_CSV), help="Path to cases.csv")
    args = ap.parse_args()

    cfg = load_config()
    cases_path = Path(args.cases)
    inbox, processed, error = resolve_inbox_dirs(cfg)

    print(f"Config: {cfg['_config_path']}")
    print(f"Inbox: {inbox}")
    print(f"Processed: {processed}")
    print(f"Error: {error}")

    rows = read_cases(cases_path)
    added = register_new_files(inbox, rows)
    stats = process_pending(rows, cfg, processed, error, dry_run=args.dry_run)
    write_cases(cases_path, rows)

    print("---")
    print(f"New files registered: {added}")
    print(f"Process stats: {stats}")
    print(f"Status summary: {summarize(rows)}")
    print(f"Updated: {cases_path}")
    print("NOTE: admin_check + web import are stubs until you provide import rules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
