#!/usr/bin/env python3
"""Resolve Medinet login: env → config.local.json → defaults.

Do not put production passwords in config.example.json.
config.local.json is gitignored.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = Path(__file__).resolve().parent / "config.local.json"
EXAMPLE_CONFIG = Path(__file__).resolve().parent / "config.example.json"

# Current PKDK Thuận Kiều login (fallback when env/config missing)
DEFAULT_USER = "pkdk_Thuankieu"
DEFAULT_PASS = "pkdk_Thuankieu#2026"


def get_medinet_creds(cfg: dict | None = None) -> tuple[str, str]:
    """Return (username, password). Prefer env, then config.local medinet.*, then defaults."""
    user = (os.environ.get("MEDINET_USER") or "").strip()
    password = (os.environ.get("MEDINET_PASS") or "").strip()

    if cfg is None:
        path = LOCAL_CONFIG if LOCAL_CONFIG.exists() else EXAMPLE_CONFIG
        if path.exists():
            try:
                cfg = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                cfg = {}
        else:
            cfg = {}

    med = (cfg or {}).get("medinet") or {}
    if not user:
        user = str(med.get("username") or med.get("user") or "").strip()
    if not password:
        password = str(med.get("password") or med.get("pass") or "").strip()

    return user or DEFAULT_USER, password or DEFAULT_PASS


def write_local_creds(username: str, password: str) -> Path:
    """Persist credentials into gitignored config.local.json."""
    if LOCAL_CONFIG.exists():
        cfg = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8-sig"))
    elif EXAMPLE_CONFIG.exists():
        cfg = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8-sig"))
    else:
        cfg = {}
    med = cfg.setdefault("medinet", {})
    med["username"] = username
    med["password"] = password
    med["date_from"] = med.get("date_from") or "01/07/2026"
    med["date_to"] = med.get("date_to") or ""
    LOCAL_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return LOCAL_CONFIG


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="Set / show Medinet login (local only)")
    ap.add_argument("--user", default="")
    ap.add_argument("--pass", dest="password", default="")
    ap.add_argument("--show", action="store_true", help="Print resolved user (mask password)")
    ap.add_argument("--write", action="store_true", help="Write --user/--pass into config.local.json")
    args = ap.parse_args()

    if args.write:
        u = args.user or DEFAULT_USER
        p = args.password or DEFAULT_PASS
        path = write_local_creds(u, p)
        print(f"OK wrote {path} user={u}")
        sys.exit(0)

    u, p = get_medinet_creds()
    if args.show:
        print(f"user={u} pass={'*' * len(p)} (len={len(p)})")
    else:
        # for PowerShell to capture: two lines
        print(u)
        print(p)
