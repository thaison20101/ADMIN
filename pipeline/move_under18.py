#!/usr/bin/env python3
"""Move under-18 PDFs into G:\\...\\PKDK_Thuankieu_Pipeline\\UNDER 18.

Rule (year-only, today): birth_year >= (current_year - 17)  → age <= 17.
Also: filename mau M1 / M2 / M12 → under 18 even if year missing.

Sources: INBOX_CLS + MISSING + ERROR (not PROCESSED).
Uses tracking CSV paths first (no 10k G: rglob). Optional --disk-scan lists
top-level PDFs via scandir.

  python .\\pipeline\\move_under18.py --dry-run
  python .\\pipeline\\move_under18.py
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from drive_paths import (  # noqa: E402
    UNDER18_FOLDER,
    count_pdfs_fast,
    ensure_standard_folders,
    g_pipeline_live,
    local_work_build,
    resolve_g_sync,
)
from hourly_sync import read_cases, write_cases  # noqa: E402
from phase_b_preview import load_config, resolve_name_year  # noqa: E402
from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()

SOURCE_TAGS = ("INBOX_CLS", "MISSING", "ERROR")
CHILD_MAU = re.compile(r"(?<![A-Z0-9])(M1|M2|M12)(?![A-Z0-9])", re.I)


def is_under18(*, nam_sinh: str, file_name: str = "", as_of: date | None = None) -> bool:
    """True if patient is under 18 years old (year-only + child mau)."""
    as_of = as_of or date.today()
    year_s = str(nam_sinh or "").strip()
    if year_s.isdigit() and len(year_s) == 4:
        y = int(year_s)
        # age = as_of.year - y; under 18 ⇒ y >= as_of.year - 17
        if y >= as_of.year - 17:
            return True
        return False
    stem = Path(file_name).stem if file_name else ""
    if CHILD_MAU.search(stem):
        return True
    return False


def _bucket(src: str) -> str:
    u = (src or "").replace("\\", "/").upper()
    for tag in SOURCE_TAGS:
        if f"/{tag}/" in u or u.endswith(f"/{tag}"):
            return tag
    if "UNDER 18" in u or "UNDER_18" in u:
        return "UNDER18"
    return ""


def _list_top_pdfs(folder: Path) -> list[Path]:
    out: list[Path] = []
    try:
        if not folder.exists():
            return out
        with __import__("os").scandir(folder) as it:
            for ent in it:
                if ent.name.lower().endswith(".pdf") and ent.is_file(follow_symlinks=False):
                    out.append(Path(ent.path))
    except Exception:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Park under-18 PDFs into UNDER 18 folder")
    ap.add_argument("--dry-run", action="store_true", help="List only, do not move")
    ap.add_argument(
        "--disk-scan",
        action="store_true",
        help="Also scandir INBOX/MISSING/ERROR top-level (CSV is default)",
    )
    ap.add_argument("--limit", type=int, default=0, help="Max moves (0=all)")
    args = ap.parse_args()

    cfg = load_config()
    if sys.platform.startswith("win") and g_pipeline_live() is None:
        safe_print("ABORT: G: chua mount — khong fallback ADMIN")
        return 2

    sync = resolve_g_sync(cfg)
    build = local_work_build()
    ensure_standard_folders(sync, build)
    dest = sync / UNDER18_FOLDER
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        safe_print(f"ABORT: khong tao {dest}: {e}")
        return 2

    cases_path = ROOT / cfg.get("tracking", {}).get("cases_csv", "tracking/cases.csv")
    rows = read_cases(cases_path)
    by_name: dict[str, dict] = {}
    for r in rows:
        nm = (Path(r.get("source_file") or "").name or r.get("file_name") or "").lower()
        if nm:
            by_name[nm] = r

    candidates: list[tuple[Path, str, str, dict | None]] = []
    # From CSV
    for r in rows:
        src = Path(r.get("source_file") or "")
        tag = _bucket(str(src))
        if tag not in SOURCE_TAGS:
            continue
        name, year = resolve_name_year(
            {
                "ho_ten": r.get("ho_ten") or "",
                "nam_sinh": r.get("nam_sinh") or "",
                "file_name": src.name or r.get("file_name") or "",
                "source_file": str(src),
            }
        )
        fname = src.name or r.get("file_name") or ""
        if not is_under18(nam_sinh=year, file_name=fname):
            continue
        pdf = src if src.suffix.lower() == ".pdf" else sync / tag / fname
        candidates.append((pdf, year or "?", tag, r))

    if args.disk_scan:
        for tag in SOURCE_TAGS:
            folder = sync / tag
            for pdf in _list_top_pdfs(folder):
                key = pdf.name.lower()
                if any(c[0].name.lower() == key for c in candidates):
                    continue
                r = by_name.get(key)
                name, year = resolve_name_year(
                    {
                        "ho_ten": (r or {}).get("ho_ten") or "",
                        "nam_sinh": (r or {}).get("nam_sinh") or "",
                        "file_name": pdf.name,
                        "source_file": str(pdf),
                    }
                )
                if not is_under18(nam_sinh=year, file_name=pdf.name):
                    continue
                candidates.append((pdf, year or "?", tag, r))

    safe_print("========== LOC UNDER 18 ==========")
    safe_print(f"SYNC: {sync}")
    safe_print(f"DEST: {dest}")
    safe_print(f"Candidates: {len(candidates)} dry_run={args.dry_run}")
    as_of = date.today()
    safe_print(f"Rule: nam_sinh >= {as_of.year - 17} (age<=17) OR mau M1/M2/M12")

    moved = 0
    missing_disk = 0
    for pdf, year, tag, row in candidates:
        if args.limit and moved >= args.limit:
            break
        try:
            exists = pdf.exists()
        except Exception:
            exists = False
        if not exists:
            # try folder/name
            alt = sync / tag / pdf.name
            try:
                if alt.exists():
                    pdf = alt
                    exists = True
            except Exception:
                pass
        if not exists:
            missing_disk += 1
            safe_print(f"SKIP missing_disk {tag}/{pdf.name} year={year}")
            continue
        target = dest / pdf.name
        if target.exists() and target.resolve() != pdf.resolve():
            target = dest / f"{pdf.stem}_u18{pdf.suffix}"
        safe_print(f"{'DRY ' if args.dry_run else ''}MOVE {tag}/{pdf.name} year={year} -> UNDER 18/")
        if args.dry_run:
            moved += 1
            continue
        try:
            shutil.move(str(pdf), str(target))
        except Exception as e:
            safe_print(f"  MOVE FAIL {pdf.name}: {e}")
            continue
        if row is not None:
            row["source_file"] = str(target)
            row["file_name"] = target.name
            # Not rematched until user moves PDF back to INBOX_CLS
            row["status"] = "PARKED_UNDER18"
            row["notes"] = f"parked_under18:{tag}:year={year}"[:200]
            if year and year.isdigit():
                row["nam_sinh"] = year
        moved += 1

    if not args.dry_run:
        write_cases(cases_path, rows)

    n_u18 = count_pdfs_fast(dest)
    safe_print(f"Moved/listed: {moved} missing_disk={missing_disk}")
    safe_print(f"UNDER 18 now: {n_u18} pdfs")
    safe_print("Khi san sang: copy/move PDF tu UNDER 18 -> INBOX_CLS roi chay rematch.")
    safe_print("==================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
