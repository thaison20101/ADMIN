"""Offline proof: repair/full-scan dirs always include PROCESSED+TK1+TK2."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PIPE = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPE))

from auto_cycle import _collect_scan_dirs  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        sync = Path(td) / "sync"
        for name in (
            "INBOX_CLS",
            "MISSING",
            "ERROR",
            "PROCESSED",
            "UNDER 18",
            "TK1",
            "TK2",
        ):
            (sync / name).mkdir(parents=True)
        inbox = sync / "INBOX_CLS"
        missing = sync / "MISSING"
        error = sync / "ERROR"
        processed = sync / "PROCESSED"

        print("=== repair bot=all ===")
        d_all = _collect_scan_dirs(
            sync, inbox, missing, error, processed, full_scan=False, repair=True, bot_role="all"
        )
        print([p.name for p in d_all])

        print("=== repair bot=missing (AUDIT PROCESSED+TK) ===")
        d_miss = _collect_scan_dirs(
            sync,
            inbox,
            missing,
            error,
            processed,
            full_scan=False,
            repair=True,
            bot_role="missing",
        )
        print([p.name for p in d_miss])

        print("=== full-scan+repair bot=missing ===")
        d_full = _collect_scan_dirs(
            sync,
            inbox,
            missing,
            error,
            processed,
            full_scan=True,
            repair=True,
            bot_role="missing",
        )
        print([p.name for p in d_full])

        for label, dirs in (("all", d_all), ("missing", d_miss), ("full_missing", d_full)):
            names = {p.name.upper() for p in dirs}
            for must in ("PROCESSED", "TK1", "TK2"):
                if must not in names:
                    print(f"FAIL {label} missing {must}")
                    return 1
            if label != "full_missing" and "MISSING" in names:
                print(f"FAIL {label} should not walk MISSING on repair-only")
                return 1
        print("OK: PROCESSED+TK1+TK2 in every fillable repair/full audit path")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
