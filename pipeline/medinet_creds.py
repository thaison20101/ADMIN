#!/usr/bin/env python3
"""Resolve Medinet login: hardcoded PKDK defaults, then env override.

config.local.json must NOT silently keep an old TK1 password (that blocked
fills after Qlskcd@2026 rotation). Known clinic accounts always use
MEDINET_ACCOUNTS unless MEDINET_USER/PASS env explicitly overrides.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = Path(__file__).resolve().parent / "config.local.json"
EXAMPLE_CONFIG = Path(__file__).resolve().parent / "config.example.json"

# Hardcoded PKDK accounts (may A) — source of truth
MEDINET_ACCOUNTS = [
    {
        "id": "pkdkthuankieu",
        "user": "pkdkthuankieu",
        "password": "Qlskcd@2026",
    },
    {
        "id": "pkdk_Thuankieu",
        "user": "pkdk_Thuankieu",
        "password": "pkdk_Thuankieu#2026",
    },
]

DEFAULT_USER = MEDINET_ACCOUNTS[0]["user"]
DEFAULT_PASS = MEDINET_ACCOUNTS[0]["password"]


def get_medinet_accounts(cfg: dict | None = None) -> list[dict]:
    """Return [{id, user, password}, ...] — always the 2 PKDK accounts.

    Env overrides (optional):
      MEDINET_USER / MEDINET_PASS       -> TK1
      MEDINET_USER_2 / MEDINET_PASS_2   -> TK2
    config.local accounts[] is ignored for passwords (was trapping old P@ssw0rd).
    """
    a1 = MEDINET_ACCOUNTS[0].copy()
    a2 = MEDINET_ACCOUNTS[1].copy()
    u1 = (os.environ.get("MEDINET_USER") or "").strip()
    p1 = (os.environ.get("MEDINET_PASS") or "").strip()
    u2 = (os.environ.get("MEDINET_USER_2") or "").strip()
    p2 = (os.environ.get("MEDINET_PASS_2") or "").strip()
    if u1:
        a1["user"] = u1
        a1["id"] = u1
    if p1:
        a1["password"] = p1
    if u2:
        a2["user"] = u2
        a2["id"] = u2
    if p2:
        a2["password"] = p2
    return [a1, a2]


def get_medinet_creds(cfg: dict | None = None) -> tuple[str, str]:
    """Primary account (first in list) — backward compatible."""
    a = get_medinet_accounts(cfg)[0]
    return a["user"], a["password"]


def write_local_creds(username: str, password: str) -> Path:
    """Persist both PKDK accounts into gitignored config.local.json."""
    if LOCAL_CONFIG.exists():
        cfg = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8-sig"))
    elif EXAMPLE_CONFIG.exists():
        cfg = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8-sig"))
    else:
        cfg = {}
    med = cfg.setdefault("medinet", {})
    med["username"] = username or DEFAULT_USER
    med["password"] = password or DEFAULT_PASS
    med["accounts"] = [a.copy() for a in MEDINET_ACCOUNTS]
    if username or password:
        med["accounts"][0]["user"] = username or DEFAULT_USER
        med["accounts"][0]["id"] = username or DEFAULT_USER
        med["accounts"][0]["password"] = password or DEFAULT_PASS
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
    ap.add_argument("--write", action="store_true", help="Write accounts into config.local.json")
    ap.add_argument("--list-accounts", action="store_true", help="List both account ids")
    args = ap.parse_args()

    if args.write:
        u = args.user or DEFAULT_USER
        p = args.password or DEFAULT_PASS
        path = write_local_creds(u, p)
        print(f"OK wrote {path} user={u}")
        sys.exit(0)

    if args.list_accounts:
        for a in get_medinet_accounts():
            print(f"{a['id']}\t{a['user']}")
        sys.exit(0)

    u, p = get_medinet_creds()
    if args.show:
        print(f"user={u} pass={'*' * len(p)} (len={len(p)})")
        accts = get_medinet_accounts()
        print(f"accounts={accts[0]['id']}+{accts[1]['id']}")
        print(f"tk1_pass_prefix={accts[0]['password'][:4]}")
    else:
        print(u)
        print(p)
