#!/usr/bin/env python3
"""Resolve Drive build_root and print/write it as UTF-8 (for PowerShell runners)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from drive_paths import discover_build_root, ensure_standard_folders, discover_pipeline_root  # noqa: E402


def resolve() -> Path:
    pipeline = discover_pipeline_root()
    build = discover_build_root()
    ensure_standard_folders(pipeline, build)
    return build


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="Write path to this UTF-8 file")
    args = ap.parse_args()
    chosen = resolve()
    text = str(chosen)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
