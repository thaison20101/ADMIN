#!/usr/bin/env python3
"""Exit 2 if pipeline root is missing G: or is the empty D: mirror.

Usage (Windows): python pipeline/assert_g_pipeline.py
Non-Windows: exit 0 (dev/CI).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from drive_paths import (  # noqa: E402
    _pdf_count,
    discover_build_root,
    discover_pipeline_root,
    g_pipeline_live,
    is_forbidden_d_pipeline,
)


def main() -> int:
    sync = discover_pipeline_root()
    build = discover_build_root()
    print(f"SYNC={sync}")
    print(f"BUILD={build}")
    if is_forbidden_d_pipeline(sync):
        print("ABORT: D:\\PKDK_Thuankieu_Pipeline is empty mirror. Mount G: Drive.")
        return 2
    if not sys.platform.startswith("win"):
        print("SKIP: not Windows")
        return 0
    live = g_pipeline_live()
    if live is None:
        print("ABORT: G:\\Drive cua toi\\PKDK_Thuankieu_Pipeline not mounted.")
        print("Open Google Drive Desktop, wait for G:, then rerun. Do not click this window.")
        return 2
    n = _pdf_count(live)
    print(f"G_PDFS={n}")
    if n == 0:
        print("ABORT: G: folder exists but 0 PDFs. Wait for Drive sync.")
        return 2
    print("OK: G: pipeline live")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
