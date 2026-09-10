#!/usr/bin/env python3
"""Print DISK PDF counts for pipeline folders (not cases.csv).

cases.csv can be empty/wiped while G: still has thousands of PDFs.
TONG_HOP must gate on DISK inventory, never trust CSV alone.

Must include every EXTRA_FOLDERS name (incl. CCCD) — never KeyError.
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


# Folder display name → short disk_* key
_NAME_TO_KEY = {
    "INBOX_CLS": "inbox",
    "MISSING": "missing",
    "ERROR": "error",
    "PROCESSED": "processed",
    UNDER18_FOLDER: "under18",
    "TK1": "tk1",
    "TK2": "tk2",
    "CCCD": "cccd",
}


def _key_for(folder_name: str) -> str:
    if folder_name in _NAME_TO_KEY:
        return _NAME_TO_KEY[folder_name]
    # Future EXTRA_FOLDERS: slugify safely (no KeyError)
    return re_slug(folder_name)


def re_slug(name: str) -> str:
    s = (name or "").strip().lower().replace(" ", "")
    return s or "unknown"


def disk_counts(sync: Path | None = None) -> dict[str, int]:
    sync = sync or discover_pipeline_root()
    build = discover_build_root()
    folders = ensure_standard_folders(sync, build)
    out: dict[str, int] = {}
    for folder_name in list(STD_FOLDERS) + list(EXTRA_FOLDERS):
        key = _key_for(folder_name)
        p = folders.get(folder_name) or (sync / folder_name)
        try:
            out[key] = count_pdfs_fast(p) if p.exists() else 0
        except Exception as exc:  # noqa: BLE001
            print(f"WARN count {folder_name}: {exc}", file=sys.stderr)
            out[key] = -1
    return out


def main() -> int:
    try:
        sync = discover_pipeline_root()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN discover_pipeline_root: {exc}", file=sys.stderr)
        print("DISK\tinbox=0\tmissing=0\terror=0\tprocessed=0\tunder18=0\ttk1=0\ttk2=0\tcccd=0")
        print("FILLABLE_DISK\t0")
        print("ARCHIVE_DISK\t0")
        print("WORK_DISK\t0")
        print("WARN_TK_EMPTY\t1")
        return 0

    c = disk_counts(sync)
    # Compat aliases for older greppers
    for k in ("inbox", "missing", "error", "processed", "under18", "tk1", "tk2", "cccd"):
        c.setdefault(k, 0)

    fillable = c["error"] + c["processed"] + c["under18"] + c["tk1"] + c["tk2"] + c["cccd"]
    work = fillable + c["inbox"] + c["missing"]
    archive = c["processed"] + c["under18"] + c["tk1"] + c["tk2"] + c["cccd"]
    print(sync)
    print(
        f"DISK\tinbox={c['inbox']}\tmissing={c['missing']}\t"
        f"error={c['error']}\tprocessed={c['processed']}\tunder18={c['under18']}"
        f"\ttk1={c['tk1']}\ttk2={c['tk2']}\tcccd={c['cccd']}"
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
    for name in list(STD_FOLDERS) + list(EXTRA_FOLDERS):
        key = _key_for(name)
        print(f"  disk_{name}: {c.get(key, 0)} pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
