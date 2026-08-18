"""Print Drive folder paths after discovery (one path per line).

Order: sync_root, inbox, error, processed, missing
Then one summary line: COUNTS inbox missing error processed
Usage: python pipeline/print_drive_dirs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from drive_paths import discover_pipeline_root, ensure_standard_folders, discover_build_root, write_resolved_into_config  # noqa: E402


def _n(p: Path) -> int:
    if not p.exists():
        return 0
    return sum(1 for _ in p.rglob("*.pdf"))


def main() -> int:
    sync = discover_pipeline_root()
    build = discover_build_root()
    ensure_standard_folders(sync, build)
    write_resolved_into_config(sync, build)
    inbox = sync / "INBOX_CLS"
    err = sync / "ERROR"
    proc = sync / "PROCESSED"
    miss = sync / "MISSING"
    print(sync)
    print(inbox)
    print(err)
    print(proc)
    print(miss)
    print(f"COUNTS\tinbox={_n(inbox)}\tmissing={_n(miss)}\terror={_n(err)}\tprocessed={_n(proc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
