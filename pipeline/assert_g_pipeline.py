#!/usr/bin/env python3
"""May A only: exit 2 unless G:\\Drive cua toi\\PKDK_Thuankieu_Pipeline is live.

Usage: python pipeline/assert_g_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from drive_paths import (  # noqa: E402
    PINNED_PIPELINE,
    discover_build_root,
    discover_pipeline_root,
    g_pipeline_live,
    is_non_g_pipeline,
    require_g_on_windows,
)


def main() -> int:
    sync = discover_pipeline_root()
    build = discover_build_root()
    print(f"SYNC={sync}")
    print(f"BUILD={build}")
    print(f"PIN={PINNED_PIPELINE}")

    if is_non_g_pipeline(sync):
        print("ABORT: o D: mirror may B — chi may A G:\\Drive cua toi\\PKDK_Thuankieu_Pipeline")
        return 2

    if not sys.platform.startswith("win"):
        print("SKIP: not Windows (dev)")
        return 0

    if not require_g_on_windows(sync):
        print(f"ABORT: sync khong phai G: — {sync}")
        return 2

    live = g_pipeline_live()
    if live is None:
        print("ABORT: G: chua mount. Mo Google Drive Desktop tren may A.")
        return 2

    # Do NOT count 10k MISSING (Drive listing hang). Light count = INBOX+ERROR+PROCESSED.
    from drive_paths import count_pdfs_fast

    light = 0
    for name in ("INBOX_CLS", "ERROR", "PROCESSED"):
        light += count_pdfs_fast(live / name)
    miss_dir = live / "MISSING"
    miss_exists = miss_dir.exists()
    print(f"G_PDFS_LIGHT={light} (INBOX+ERROR+PROCESSED; skip listing MISSING)")
    if light == 0 and not miss_exists:
        print("ABORT: G: co folder nhung 0 PDF — doi Drive sync.")
        return 2

    print("OK: may A G: pipeline live")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
