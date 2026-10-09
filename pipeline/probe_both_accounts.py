#!/usr/bin/env python3
"""Probe Medinet accounts. Exit 0 if TK1 OK (TK2 soft-fail with warn). Exit 2 if TK1 fails."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("MEDINET_SSL_VERIFY", "0")
sys.path.insert(0, str(__file__).rsplit("/", 1)[0] if "/" in __file__ else ".")

from medinet_ssl import install_medinet_https_opener, reset_ssl_cache  # noqa: E402


def main() -> int:
    reset_ssl_cache()
    install_medinet_https_opener()
    from medinet_api import login_accounts
    from medinet_creds import get_medinet_accounts

    accounts = get_medinet_accounts()
    try:
        working, tokens = login_accounts(accounts, require_first=True)
    except Exception as e:
        print(f"AUTH_FAIL TK1: {e}")
        return 2
    ids = "+".join(a["id"] for a in working)
    print(f"AUTH_READY accounts={ids} n={len(working)}")
    if len(working) < len(accounts):
        print("AUTH_READY: TK2 skip (sai pass / khoa) - dien INBOX bang TK1")
    # tokens unused; just prove login
    _ = tokens
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
