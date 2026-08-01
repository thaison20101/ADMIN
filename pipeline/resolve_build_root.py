#!/usr/bin/env python3
"""Resolve Drive build_root and print/write it as UTF-8 (for PowerShell runners)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_raw() -> str:
    for p in (ROOT / "pipeline" / "config.local.json", ROOT / "pipeline" / "config.example.json"):
        if p.exists():
            cfg = json.loads(p.read_text(encoding="utf-8-sig"))
            return str((cfg.get("drive") or {}).get("build_root") or "")
    return ""


def candidates(raw: str) -> list[Path]:
    out: list[Path] = []
    if raw:
        out.append(Path(raw))
    for drive in ("G:", "H:", "D:"):
        for mid in ("Drive của tôi", "Drive của Tôi", "My Drive", "Drive cua toi"):
            out.append(Path(f"{drive}/{mid}/build for Supper Data"))
    out.append(ROOT / "pipeline" / "work" / "build")
    # dedupe
    seen = set()
    uniq = []
    for p in out:
        k = str(p).lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq


def resolve() -> Path:
    opts = candidates(load_raw())
    for p in opts:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    p = opts[0]
    p.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="Write path to this UTF-8 file")
    args = ap.parse_args()
    chosen = resolve()
    for sub in ("logs", "excel_preview", "missing_or_updated", "cases_snapshot"):
        (chosen / sub).mkdir(parents=True, exist_ok=True)
    text = str(chosen)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    # Also print ASCII-safe marker + path for debugging
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
