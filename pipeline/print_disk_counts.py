#!/usr/bin/env python3
"""Print DISK PDF counts for pipeline folders (not cases.csv).

cases.csv can be empty/wiped while G: still has thousands of PDFs.
TONG_HOP must gate on DISK inventory, never trust CSV alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from drive_paths import (  # noqa: E402
    EXTRA_FOLDERS,
    STD_FOLDERS,
    UNDER18_FOLDER,
    count_pdfs_fast,
    discover_pipeline_root,
    ensure_standard_folders,
    discover_build_root,
)


def disk_counts(sync: Path | None = None) -> dict[str, int]:
    sync = sync or discover_pipeline_root()
    build = discover_build_root()
    folders = ensure_standard_folders(sync, build)
    out = {
        "inbox": 0,
        "missing": 0,
        "error": 0,
        "processed": 0,
        "under18": 0,
        "tk1": 0,
        "tk2": 0,
    }
    name_map = {
        "INBOX_CLS": "inbox",
        "MISSING": "missing",
        "ERROR": "error",
        "PROCESSED": "processed",
        UNDER18_FOLDER: "under18",
        "TK1": "tk1",
        "TK2": "tk2",
    }
    for folder_name, key in name_map.items():
        p = folders.get(folder_name) or (sync / folder_name)
        out[key] = count_pdfs_fast(p) if p.exists() else 0
    return out


def main() -> int:
    sync = discover_pipeline_root()
    c = disk_counts(sync)
    fillable = c["error"] + c["processed"] + c["under18"] + c["tk1"] + c["tk2"]
    # Full scan also walks MISSING (bot missing) + INBOX
    work = fillable + c["inbox"] + c["missing"]
    archive = c["processed"] + c["under18"] + c["tk1"] + c["tk2"]
    print(sync)
    print(
        f"DISK\tinbox={c['inbox']}\tmissing={c['missing']}\t"
        f"error={c['error']}\tprocessed={c['processed']}\tunder18={c['under18']}"
        f"\ttk1={c['tk1']}\ttk2={c['tk2']}"
    )
    print(f"FILLABLE_DISK\t{fillable}")
    print(f"ARCHIVE_DISK\t{archive}")
    print(f"WORK_DISK\t{work}")
    if c["tk1"] == 0 and c["tk2"] == 0:
        print("WARN_TK_EMPTY\t1")
        print(
            "WARN: TK1+TK2 disk=0 — bat 'Available offline' tren G:\\...\\TK1 va TK2 "
            "(Google Drive Desktop). Khong danh FULL_DONE khi TK trong."
        )
    else:
        print("WARN_TK_EMPTY\t0")
    # Also print STD+EXTRA lines for humans
    for name in list(STD_FOLDERS) + list(EXTRA_FOLDERS):
        key = {
            "INBOX_CLS": "inbox",
            "MISSING": "missing",
            "ERROR": "error",
            "PROCESSED": "processed",
            UNDER18_FOLDER: "under18",
            "TK1": "tk1",
            "TK2": "tk2",
        }[name]
        print(f"  disk_{name}: {c[key]} pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
