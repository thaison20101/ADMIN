#!/usr/bin/env python3
"""Mirror pipeline status to G:\\Drive cua toi\\build for Supper Data (theo doi)."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from drive_paths import g_pipeline_live, local_work_build

G_SUPER_DATA_VARIANTS = (
    Path(r"G:/Drive của tôi/build for Supper Data"),
    Path(r"G:/Drive cua toi/build for Supper Data"),
    Path(r"G:/My Drive/build for Supper Data"),
)

FEATURES_DONE = """
TINH NANG DA TRIEN KHAI (branch cursor/drive-hourly-pipeline-df0f)
================================================================
1. Khop TTHC: CHINH XAC ho + ten + nam sinh (verify_tthc_record)
2. DIEN CLS tu PDF vao form Can lam sang (khong bo sot field, doi don vi)
3. FULL TTHC + FULL CLS -> PROCESSED (nguoi lon) / UNDER 18 (tre FULL)
4. Co TTHC + PARTIAL CLS -> dien phan co trong PDF -> ERROR
5. Khong TTHC tren CA 2 TK Medinet -> MISSING (NO_TTHC_BOTH)
6. Loi PDF / khong co nam sinh -> UNDER 18 (folder kiem tra tay)
7. 2 TK Medinet (index + live search gop):
   - pkdkthuankieu / P@ssw0rd
   - pkdk_Thuankieu / pkdk_Thuankieu#2026
   - TTHC nhap tren TK1 co the khong thay tren TK2 -> quet ca 2
8. 2 bot song song: inbox (INBOX_CLS) + missing (MISSING CSV)
   - Claim PDF/pid tranh trung lap
   - Merge cases.csv khi 2 bot chay
9. Hourly: 2 bot INBOX_CLS + MISSING rematch (2 TK, 2500 MISSING/vong)
10. Lan dau: full-scan toan folder; sau do hourly nhe
11. Urea: dien khi PDF co (mg/dL -> mmol/L)

LENH CHAY MAY A (1 LENH DUY NHAT)
---------------------------------
cd C:\\Users\\thais\\ADMIN
powershell -ExecutionPolicy Bypass -File .\\pipeline\\CHAY_TONG_HOP_MOI.ps1

(Lenh tren: tat hourly -> pull -> full 2 bot -> rematch MISSING -> Urea -> bat hourly)

2 bot song song (INBOX + MISSING, khong full):
  powershell -ExecutionPolicy Bypass -File .\\pipeline\\CHAY_2_BOT_SONG_SONG.ps1

Dong bo folder G:
  powershell -ExecutionPolicy Bypass -File .\\pipeline\\CHAY_DONG_BO_DRIVE.ps1

Cap nhat file theo doi len G (build for Supper Data):
  python pipeline/super_data_status.py --publish

FOLDER PDF
----------
G:\\Drive cua toi\\PKDK_Thuankieu_Pipeline\\
  INBOX_CLS  = PDF moi
  MISSING    = chua TTHC
  ERROR      = PARTIAL / thieu field
  PROCESSED  = FULL nguoi lon
  UNDER 18   = tre FULL HOAC loi PDF / thieu nam sinh (kiem tra)

FILE THEO DOI (local + copy sang G)
-----------------------------------
pipeline\\work\\build\\TIEN_DO_THEO_DOI.txt   (file nay)
pipeline\\work\\build\\last_counts.txt
pipeline\\work\\build\\logs\\LAST_HOURLY_OK.txt
pipeline\\work\\build\\logs\\last_moves.txt
pipeline\\work\\build\\excel_preview\\missing_can_tthc.txt
"""


def g_super_data_build_live() -> Path | None:
    """G: build for Supper Data if Google Drive mounted."""
    if g_pipeline_live() is None:
        return None
    for p in G_SUPER_DATA_VARIANTS:
        try:
            parent = p.parent
            if parent.exists():
                p.mkdir(parents=True, exist_ok=True)
                return p
        except Exception:
            continue
    return None


def ensure_super_data_dirs(g_build: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for name in ("logs", "excel_preview", "missing_or_updated", "cases_snapshot"):
        p = g_build / name
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        out[name] = p
    return out


def _copy_if_exists(src: Path, dest: Path) -> bool:
    try:
        if not src.exists() or not src.is_file():
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return True
    except Exception:
        return False


def publish_super_data_status(
    *,
    local_build: Path | None = None,
    summary: dict | None = None,
    counts_line: str = "",
    mode: str = "",
    extra_lines: list[str] | None = None,
) -> Path | None:
    """Write TIEN_DO_THEO_DOI.txt locally and mirror to G: build for Supper Data."""
    local = local_build or local_work_build()
    local.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    lines = [
        "=== TIEN DO PIPELINE PKDK THUAN KIEU ===",
        f"Cap nhat: {now}",
        f"Mode: {mode or (summary or {}).get('mode', '')}",
        "",
    ]
    if counts_line:
        lines.append(f"COUNTS: {counts_line}")
        lines.append("")
    if summary:
        lines.append("VONG CHAY VUA XONG:")
        for k in (
            "imported",
            "imported_partial_to_error",
            "waiting_admin",
            "moved_missing",
            "routed_review_u18",
            "evicted_processed",
            "skipped_claim",
            "tthc_strict_reject",
            "live_name_match",
            "unmatched_no_year",
            "queued",
            "new_files",
        ):
            if k in summary and summary[k]:
                lines.append(f"  {k}={summary[k]}")
        lines.append("")

    if extra_lines:
        lines.extend(extra_lines)
        lines.append("")

    lines.append(FEATURES_DONE.strip())
    body = "\n".join(lines) + "\n"

    local_status = local / "TIEN_DO_THEO_DOI.txt"
    local_status.write_text(body, encoding="utf-8")

    # Mirror key artifacts local -> G
    mirror_pairs = [
        (local / "last_counts.txt", "last_counts.txt"),
        (local / "logs" / "LAST_HOURLY_OK.txt", "logs/LAST_HOURLY_OK.txt"),
        (local / "logs" / "last_moves.txt", "logs/last_moves.txt"),
        (local / "excel_preview" / "missing_can_tthc.txt", "excel_preview/missing_can_tthc.txt"),
        (local_status, "TIEN_DO_THEO_DOI.txt"),
    ]

    g_build = g_super_data_build_live()
    if g_build is None:
        return local_status

    ensure_super_data_dirs(g_build)
    copied = 0
    for src, rel in mirror_pairs:
        if _copy_if_exists(src, g_build / rel):
            copied += 1

    # Snapshot status history on G
    hist = g_build / "logs" / f"tien_do_{stamp}.txt"
    try:
        hist.write_text(body, encoding="utf-8")
    except Exception:
        pass

    return g_build / "TIEN_DO_THEO_DOI.txt"


def main() -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Publish pipeline status to G build for Supper Data")
    ap.add_argument("--publish", action="store_true", help="Write + mirror TIEN_DO_THEO_DOI.txt")
    ap.add_argument("--json", action="store_true", help="Print G build path as JSON")
    args = ap.parse_args()

    g = g_super_data_build_live()
    local = local_work_build()
    info = {
        "local_build": str(local),
        "g_super_data_build": str(g) if g else None,
        "g_live": g is not None,
    }
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print(f"LOCAL: {local}")
        print(f"G BUILD: {g or 'G: chua mount'}")

    if args.publish:
        dest = publish_super_data_status(local_build=local, mode="manual")
        print(f"OK: {dest}")
    return 0 if g else 2


if __name__ == "__main__":
    raise SystemExit(main())
