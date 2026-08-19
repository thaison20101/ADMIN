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
    _pdf_count,
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

    n = _pdf_count(live)
    print(f"G_PDFS={n}")
    if n == 0:
        print("ABORT: G: co folder nhung 0 PDF — doi Drive sync.")
        return 2

    print("OK: may A G: pipeline live")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
