#!/usr/bin/env python3
"""Ensure pipeline/config.local.json exists with safe defaults for one-shot/hourly runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = Path(__file__).resolve().parent / "config.local.json"
EXAMPLE = Path(__file__).resolve().parent / "config.example.json"

# ASCII-only path literals; resolve_build_root handles real Drive folder names.
DEFAULT_SYNC = r"G:/Drive cua toi/PKDK_Thuankieu_Pipeline"
DEFAULT_BUILD = r"G:/Drive cua toi/build for Supper Data"


def main() -> int:
    if not CFG.exists():
        if EXAMPLE.exists():
            CFG.write_text(EXAMPLE.read_text(encoding="utf-8-sig"), encoding="utf-8")
        else:
            CFG.write_text("{}", encoding="utf-8")

    cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
    drive = cfg.setdefault("drive", {})
    # Keep existing paths if already set (may contain Vietnamese folder names)
    drive.setdefault("local_sync_root", DEFAULT_SYNC)
    drive.setdefault("build_root", DEFAULT_BUILD)
    drive.setdefault("inbox_folder", "INBOX_CLS")
    drive.setdefault("processed_folder", "PROCESSED")
    drive.setdefault("error_folder", "ERROR")

    med = cfg.setdefault("medinet", {})
    med["date_from"] = med.get("date_from") or "01/07/2026"
    med["date_to"] = ""  # empty = today in auto_cycle

    rules = cfg.setdefault("import_rules", {})
    rules["enabled"] = True
    rules["auto_hourly"] = True
    rules["max_imports_per_run"] = int(rules.get("max_imports_per_run") or 200)

    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("config OK", drive.get("local_sync_root"), "date_to=today")
    return 0


if __name__ == "__main__":
    sys.exit(main())
