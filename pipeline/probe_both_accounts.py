#!/usr/bin/env python3
"""Probe Medinet AUTH + DRViewer + FormViewer CLS. Exit 0 if can fill CLS."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("MEDINET_SSL_VERIFY", "0")
sys.path.insert(0, str(__file__).rsplit("/", 1)[0] if "/" in __file__ else ".")

from medinet_ssl import install_medinet_https_opener, reset_ssl_cache  # noqa: E402


def main() -> int:
    reset_ssl_cache()
    install_medinet_https_opener()
    from medinet_api import assert_can_fill_or_raise, login_accounts
    from medinet_creds import get_medinet_accounts, tk2_enabled

    accounts = get_medinet_accounts()
    if not tk2_enabled():
        print("AUTH_MODE: TK1 only (bo qua TK2)")
    try:
        working, tokens = login_accounts(accounts, require_first=True)
    except Exception as e:
        print(f"AUTH_FAIL TK1: {e}")
        return 2
    ids = "+".join(a["id"] for a in working)
    print(f"AUTH_READY accounts={ids} n={len(working)}")
    try:
        caps = assert_can_fill_or_raise(tokens)
    except Exception as e:
        print(f"AUTH_FAIL FILL: {e}")
        print("DUNG: TK1 login OK nhung DRViewer va FormViewer deu bi chan.")
        print("Bo qua TK2. Bao Medinet/IT cap quyen cho pkdkthuankieu.")
        return 2
    if caps.get("drviewer_ok"):
        print("AUTH_READY DRViewer OK - co the index TTHC + dien CLS (Set)")
        return 0
    # FormViewer-only: light fill when phieukhamId known; rematch live needs DRViewer
    print(
        "AUTH_READY FormViewer OK (DRViewer DENIED) - "
        "dien CLS nhe qua FormViewer; rematch ten/index can DRViewer"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
