"""Print Drive folder paths from config.local.json (one path per line).

Order: sync_root, inbox, error, processed, missing
Usage: python pipeline/print_drive_dirs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
cfg_path = ROOT / "config.local.json"
if not cfg_path.exists():
    print("ERR: missing pipeline/config.local.json", file=sys.stderr)
    raise SystemExit(1)

c = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
d = c.get("drive") or {}
s = d.get("local_sync_root") or ""
if not s:
    print("ERR: drive.local_sync_root empty", file=sys.stderr)
    raise SystemExit(1)

sep = "\\"
print(s)
print(s + sep + d.get("inbox_folder", "INBOX_CLS"))
print(s + sep + d.get("error_folder", "ERROR"))
print(s + sep + d.get("processed_folder", "PROCESSED"))
print(s + sep + d.get("missing_folder", "MISSING"))
