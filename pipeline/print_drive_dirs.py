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

from drive_paths import (  # noqa: E402
    discover_pipeline_root,
    ensure_standard_folders,
    discover_build_root,
    write_resolved_into_config,
    is_non_g_pipeline,
    require_g_on_windows,
)


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
    print(f"BUILD {build}")
    print(f"COUNTS\tinbox={_n(inbox)}\tmissing={_n(miss)}\terror={_n(err)}\tprocessed={_n(proc)}")
    if is_non_g_pipeline(sync):
        print("ABORT: o D: mirror may B — chi may A G:")
        return 2
    import sys as _sys
    if _sys.platform.startswith("win") and not require_g_on_windows(sync):
        print("ABORT: chi G:\\Drive cua toi\\PKDK_Thuankieu_Pipeline (may A)")
        return 2
    if _n(inbox) + _n(miss) + _n(err) + _n(proc) == 0:
        print("WARN: 0 PDFs in INBOX/MISSING/ERROR/PROCESSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
