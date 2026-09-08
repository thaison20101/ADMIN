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

# May A: disable SSL verify BEFORE any Medinet import
os.environ.setdefault("MEDINET_SSL_VERIFY", "0")
try:
    import medinet_ssl  # noqa: F401,E402

    medinet_ssl.apply_ssl_monkeypatch()
    medinet_ssl.install_medinet_https_opener()
except Exception as _ssl_e:
    print(f"WARN medinet_ssl bootstrap: {_ssl_e}", file=sys.stderr)

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


def name_digest(path: Path | str) -> str:
    """Stable id from filename only — never opens the file (safe on G: Drive)."""
    name = Path(path).name.lower()
    return "name:" + hashlib.sha256(name.encode("utf-8", errors="replace")).hexdigest()


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


def register_new_files(
    inbox: Path, rows: list[dict], *, hash_content: bool = True, budget: int = 0
) -> int:
    """Register PDFs under inbox. hash_content=False = name-only (G: Drive safe).

    budget: if >0, stop after that many new rows (avoid overnight Drive hydrate).
    """
    by_hash = {r.get("file_hash"): r for r in rows if r.get("file_hash")}
    by_key = {r.get("case_key"): r for r in rows if r.get("case_key")}
    by_name = {
        Path(r.get("source_file") or "").name.lower(): r
        for r in rows
        if (r.get("source_file") or r.get("file_name"))
    }
    for r in rows:
        fn = (r.get("file_name") or "").lower()
        if fn:
            by_name.setdefault(fn, r)
    added = 0
    try:
        paths = sorted(inbox.rglob("*"))
    except Exception as e:
        safe_print(f"WARN register_new_files list {inbox}: {e}")
        return 0
    for path in paths:
        if budget > 0 and added >= budget:
            safe_print(f"register_new_files budget={budget} stop at {inbox.name}")
            break
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
            continue
        key = path.name.lower()
        if key in by_name:
            continue
        if hash_content:
            try:
                digest = sha256_file(path)
            except Exception as e:
                safe_print(f"WARN sha256 skip {path.name}: {e}")
                digest = name_digest(path)
        else:
            digest = name_digest(path)
        if digest in by_hash:
            # Retarget existing hash row to this path
            old = by_hash[digest]
            old["source_file"] = str(path)
            old["file_name"] = path.name
            by_name[key] = old
            continue
        hints = parse_filename_hints(path.name)
        case_key = hints.get("ma_phieu") or digest[:16]
        if case_key in by_key:
            case_key = f"{case_key}_{digest[-8:]}"
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
        by_name[key] = row
        added += 1
        safe_print(f"+ NEW_LAB {case_key} <- {path.name}")
    return added


def seed_missing_names_fast(missing: Path, rows: list[dict], budget: int = 2500) -> int:
    """Scandir MISSING top-level names only — no open/hash/rglob (Drive-safe).

    Seeds empty cases.csv so rematch rounds can drain MISSING without hanging.
    """
    from drive_paths import count_pdfs_fast

    if not missing.exists() or budget <= 0:
        return 0
    by_name = {
        Path(r.get("source_file") or "").name.lower(): r
        for r in rows
        if r.get("source_file") or r.get("file_name")
    }
    for r in rows:
        fn = (r.get("file_name") or "").lower()
        if fn:
            by_name.setdefault(fn, r)
    added = 0
    try:
        import os

        entries: list[Path] = []
        with os.scandir(missing) as it:
            for ent in it:
                if ent.name.startswith("."):
                    continue
                if ent.name.lower().endswith(".pdf"):
                    entries.append(Path(ent.path))
                elif ent.is_dir(follow_symlinks=False):
                    # one nested level only (same as count_pdfs_fast)
                    try:
                        with os.scandir(ent.path) as sub:
                            for s in sub:
                                if s.name.lower().endswith(".pdf"):
                                    entries.append(Path(s.path))
                    except Exception:
                        continue
        entries.sort(key=lambda p: p.name.lower())
    except Exception as e:
        safe_print(f"WARN seed_missing scandir: {e}")
        return 0
    for path in entries:
        if added >= budget:
            break
        key = path.name.lower()
        if key in by_name:
            continue
        hints = parse_filename_hints(path.name)
        digest = name_digest(path)
        case_key = hints.get("ma_phieu") or digest[-16:]
        row = {
            "case_key": case_key,
            "source_file": str(path),
            "file_hash": digest,
            "file_name": path.name,
            "ho_ten": hints.get("ho_ten", ""),
            "cccd": "",
            "ngay_kham": hints.get("ngay_kham", ""),
            "mau_kham": hints.get("mau_kham", ""),
            "ma_phieu": hints.get("ma_phieu", ""),
            "has_lab_file": "YES",
            "has_admin_info": "",
            "status": "WAITING_ADMIN",
            "import_attempts": "0",
            "last_checked_at": now_iso(),
            "imported_at": "",
            "notes": "seed_missing_scandir_nohash",
        }
        rows.append(row)
        by_name[key] = row
        added += 1
    if added:
        safe_print(
            f"MISSING seed scandir (no hash): +{added} "
            f"(disk~{count_pdfs_fast(missing)}, budget={budget})"
        )
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
