#!/usr/bin/env python3
"""Resolve Medinet login: env -> config.local.json -> hardcoded defaults.

PKDK Thuận Kiều has 2 Medinet accounts; TTHC entered on one may be invisible
on the other until merged at report level. Pipeline indexes BOTH accounts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = Path(__file__).resolve().parent / "config.local.json"
EXAMPLE_CONFIG = Path(__file__).resolve().parent / "config.example.json"

# Hardcoded PKDK accounts (may A) — override via env if needed
MEDINET_ACCOUNTS = [
    {
        "id": "pkdkthuankieu",
        "user": "pkdkthuankieu",
        "password": "P@ssw0rd",
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
    """Return [{id, user, password}, ...] — always at least 2 PKDK accounts."""
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
    raw = med.get("accounts")
    if isinstance(raw, list) and len(raw) >= 2:
        out = []
        for i, item in enumerate(raw[:2]):
            if not isinstance(item, dict):
                continue
            uid = str(item.get("id") or item.get("user") or f"acct{i}").strip()
            user = str(item.get("user") or item.get("username") or "").strip()
            password = str(item.get("password") or item.get("pass") or "").strip()
            if user and password:
                out.append({"id": uid, "user": user, "password": password})
        if len(out) >= 2:
            return out

    # Env override for account 1 / 2
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
    else:
        print(u)
        print(p)
