#!/usr/bin/env python3
"""Resolve Medinet login: hardcoded PKDK defaults, then env override.

config.local.json must NOT silently keep an old TK1 password (that blocked
fills after Qlskcd@2026 rotation).

Default: CHI TK1 (pkdkthuankieu). Bo qua TK2 cho den khi MEDINET_ENABLE_TK2=1.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = Path(__file__).resolve().parent / "config.local.json"
EXAMPLE_CONFIG = Path(__file__).resolve().parent / "config.example.json"

# Hardcoded PKDK accounts (may A) — source of truth
MEDINET_TK1 = {
    "id": "pkdkthuankieu",
    "user": "pkdkthuankieu",
    "password": "Qlskcd@2026",
}
MEDINET_TK2 = {
    "id": "pkdk_Thuankieu",
    "user": "pkdk_Thuankieu",
    "password": "pkdk_Thuankieu#2026",
}
# Legacy list (tests / write_local); runtime uses get_medinet_accounts()
MEDINET_ACCOUNTS = [MEDINET_TK1, MEDINET_TK2]

DEFAULT_USER = MEDINET_TK1["user"]
DEFAULT_PASS = MEDINET_TK1["password"]


def tk2_enabled() -> bool:
    """TK2 off by default. Set MEDINET_ENABLE_TK2=1 to include again."""
    return (os.environ.get("MEDINET_ENABLE_TK2") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_medinet_accounts(cfg: dict | None = None) -> list[dict]:
    """Return active Medinet accounts. Default: TK1 only (skip TK2).

    Env:
      MEDINET_USER / MEDINET_PASS           -> TK1
      MEDINET_ENABLE_TK2=1                  -> include TK2
      MEDINET_USER_2 / MEDINET_PASS_2       -> TK2 (only if enabled)
    config.local accounts[] ignored for passwords.
    """
    a1 = MEDINET_TK1.copy()
    u1 = (os.environ.get("MEDINET_USER") or "").strip()
    p1 = (os.environ.get("MEDINET_PASS") or "").strip()
    if u1:
        a1["user"] = u1
        a1["id"] = u1
    if p1:
        a1["password"] = p1
    out = [a1]
    if not tk2_enabled():
        return out
    a2 = MEDINET_TK2.copy()
    u2 = (os.environ.get("MEDINET_USER_2") or "").strip()
    p2 = (os.environ.get("MEDINET_PASS_2") or "").strip()
    if u2:
        a2["user"] = u2
        a2["id"] = u2
    if p2:
        a2["password"] = p2
    out.append(a2)
    return out


def get_medinet_creds(cfg: dict | None = None) -> tuple[str, str]:
    """Primary account (first in list) — backward compatible."""
    a = get_medinet_accounts(cfg)[0]
    return a["user"], a["password"]


def write_local_creds(username: str, password: str) -> Path:
    """Persist TK1 (and TK2 stub if enabled) into gitignored config.local.json."""
    if LOCAL_CONFIG.exists():
        cfg = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8-sig"))
    elif EXAMPLE_CONFIG.exists():
        cfg = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8-sig"))
    else:
        cfg = {}
    med = cfg.setdefault("medinet", {})
    med["username"] = username or DEFAULT_USER
    med["password"] = password or DEFAULT_PASS
    active = get_medinet_accounts()
    med["accounts"] = [a.copy() for a in active]
    if username or password:
        med["accounts"][0]["user"] = username or DEFAULT_USER
        med["accounts"][0]["id"] = username or DEFAULT_USER
        med["accounts"][0]["password"] = password or DEFAULT_PASS
    med["skip_tk2"] = not tk2_enabled()
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
    ap.add_argument("--list-accounts", action="store_true", help="List active account ids")
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
        ids = "+".join(a["id"] for a in accts)
        print(f"accounts={ids}")
        print(f"tk1_pass_prefix={accts[0]['password'][:4]}")
        print(f"skip_tk2={not tk2_enabled()} (set MEDINET_ENABLE_TK2=1 de bat TK2)")
    else:
        print(u)
        print(p)
