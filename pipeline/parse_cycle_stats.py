"""Parse hourly_sync stdout for round counters (PowerShell-safe).

Prints one line: imported queued_total partial moved_missing audit_missing
Usage: python pipeline/parse_cycle_stats.py < logfile.txt
       python pipeline/parse_cycle_stats.py   (reads stdin)
"""
from __future__ import annotations

import re
import sys


def parse(text: str) -> dict[str, int]:
    def grab(key: str) -> int:
        m = re.search(rf"'{key}':\s*(\d+)", text)
        return int(m.group(1)) if m else 0

    queued = grab("queued") + grab("queued_incomplete")
    return {
        "imported": grab("imported"),
        "queued": queued,
        "partial": grab("imported_partial_to_error"),
        "moved_missing": grab("moved_missing"),
        "audit_missing": grab("audit_moved_missing"),
        "repair": grab("repair_incomplete") + grab("repair_empty"),
    }


def main() -> int:
    text = sys.stdin.read() if not sys.argv[1:] else Path_read(sys.argv[1])
    s = parse(text)
    print(
        "{imported} {queued} {partial} {moved_missing} {audit_missing} {repair}".format(
            **s
        )
    )
    return 0


def Path_read(p: str) -> str:
    from pathlib import Path

    return Path(p).read_text(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
