#!/usr/bin/env python3
"""Hourly pipeline: Drive INBOX_CLS + MISSING → match Medinet → auto-import CLS.

Flow each hour (laptop on + Task Scheduler + Google Drive sync):
1) Scan INBOX_CLS disk; rematch MISSING + TK1/TK2 via cases.csv (no G: list TK)
2) Match TTHC: ho+ten DAY DU + nam/ngay sinh/SDT/CCCD (thieu OK neu khong conflict)
3) Unique ten khong param -> dien; trung ten >=2 -> UNDER 18
4) Dual-write CLS ca 2 TK khi ca 2 co TTHC
5) Route: 2TK+FULL->PROCESSED/U18 | 1TK+FULL->TK1/TK2
   PARTIAL/OTHER->ERROR | noTTHC->MISSING
6) Write result Excel + heartbeat under local pipeline/work/build (never G:)

Full catch-up: python hourly_sync.py --full-scan --repair
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()

DEFAULT_CONFIG = ROOT / "pipeline" / "config.example.json"
LOCAL_CONFIG = ROOT / "pipeline" / "config.local.json"
CASES_CSV = ROOT / "tracking" / "cases.csv"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def load_config() -> dict:
    path = LOCAL_CONFIG if LOCAL_CONFIG.exists() else DEFAULT_CONFIG
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
    from csv_io import open_csv_read

    with open_csv_read(path, newline="") as f:
        return list(csv.DictReader(f))


def write_cases(path: Path, rows: list[dict]) -> None:
    """Rewrite ledger as clean UTF-8 (heals mixed-encoding corruption)."""
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
    stem = Path(name).stem
    out = {"ho_ten": "", "cccd": "", "ngay_kham": "", "mau_kham": "", "ma_phieu": ""}
    parts = [p.strip() for p in re.split(r"\s+-\s+", stem)]
    if len(parts) >= 2:
        out["ho_ten"] = parts[1]
    if parts:
        m = re.match(r"(\d{6})-(\d+)", parts[0])
        if m:
            ddmmyy, _seq = m.groups()
            dd, mm, yy = ddmmyy[:2], ddmmyy[2:4], ddmmyy[4:6]
            out["ngay_kham"] = f"20{yy}-{mm}-{dd}"
            out["ma_phieu"] = parts[0]
    m = re.search(r"\b(M1{0,2}|M2|M3|M4|M11|M12|M13)\b", stem, re.I)
    if m:
        out["mau_kham"] = m.group(1).upper()
    return out


def register_new_files(inbox: Path, rows: list[dict]) -> int:
    by_hash = {r.get("file_hash"): r for r in rows if r.get("file_hash")}
    by_key = {r.get("case_key"): r for r in rows if r.get("case_key")}
    added = 0
    for path in sorted(inbox.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
            continue
        digest = sha256_file(path)
        if digest in by_hash:
            continue
        hints = parse_filename_hints(path.name)
        case_key = hints.get("ma_phieu") or digest[:16]
        if case_key in by_key:
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
        safe_print(f"+ NEW_LAB {case_key} <- {path.name}")
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description="Hourly Drive→Medinet CLS auto import")
    ap.add_argument("--dry-run", action="store_true", help="Parse/match only, do not write Medinet")
    ap.add_argument("--limit", type=int, default=0, help="Max imports this run (0=config default)")
    ap.add_argument("--force", action="store_true", help="Overwrite CLS if already present")
    ap.add_argument(
        "--repair",
        action="store_true",
        help="Repair false IMPORTED / ERROR_IMPORT (re-import if web empty)",
    )
    ap.add_argument(
        "--missing-budget",
        type=int,
        default=-1,
        help="Cap MISSING rematch this run (-1=hourly 1500; 0=none; >0=cap). INBOX unlimited.",
    )
    ap.add_argument(
        "--full-scan",
        action="store_true",
        help="Quet TOAN BO folder (ke ca PROCESSED) de bat so BN cu",
    )
    ap.add_argument(
        "--audit-processed",
        action="store_true",
        help="Re-check PROCESSED; no strict TTHC match -> move MISSING",
    )
    ap.add_argument("--register-only", action="store_true", help="Only register inbox files, no import")
    ap.add_argument(
        "--bot",
        choices=["all", "inbox", "missing"],
        default="all",
        help="Parallel bot: inbox=INBOX_CLS only; missing=MISSING CSV only",
    )
    args = ap.parse_args()

    cfg = load_config()
    safe_print(f"Config: {cfg['_config_path']}")

    if args.register_only:
        from drive_paths import g_pipeline_live, resolve_g_sync

        if sys.platform.startswith("win") and g_pipeline_live() is None:
            safe_print("ABORT: G: chua mount — khong register vao ADMIN local")
            return 2
        sync = resolve_g_sync(cfg)
        inbox = sync / cfg["drive"].get("inbox_folder", "INBOX_CLS")
        if g_pipeline_live() is not None:
            inbox.mkdir(parents=True, exist_ok=True)
        rows = read_cases(CASES_CSV)
        added = register_new_files(inbox, rows) if inbox.exists() else 0
        write_cases(CASES_CSV, rows)
        safe_print(f"Registered {added}; ledger {CASES_CSV}")
        return 0

    # Full auto cycle (register + parse + import)
    from auto_cycle import run_auto_cycle

    summary = run_auto_cycle(
        dry_run=args.dry_run,
        limit=args.limit,
        force=args.force,
        repair=args.repair,
        full_scan=args.full_scan,
        audit_processed=args.audit_processed,
        missing_budget=args.missing_budget,
        bot_role=args.bot,
    )
    safe_print(f"Done: {summary}")
    if summary.get("abort"):
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UnicodeDecodeError as e:
        safe_print(f"FATAL encoding: {e}")
        safe_print("Fix: python pipeline/repair_cases_encoding.py")
        raise SystemExit(1)
