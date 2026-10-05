#!/usr/bin/env python3
"""Probe auth for both Medinet accounts. Exit 0 if both OK, else 2."""
from __future__ import annotations

import os
import sys

os.environ.setdefault("MEDINET_SSL_VERIFY", "0")
sys.path.insert(0, str(__file__).rsplit("/", 1)[0] if "/" in __file__ else ".")

from medinet_ssl import install_medinet_https_opener, reset_ssl_cache  # noqa: E402


def main() -> int:
    reset_ssl_cache()
    install_medinet_https_opener()
    from medinet_api import authenticate
    from medinet_creds import get_medinet_accounts

    ok = True
    for a in get_medinet_accounts():
        try:
            tok = authenticate(a["user"], a["password"])
            print(f"AUTH_OK {a['user']} token_len={len(tok or '')}")
        except Exception as e:
            print(f"AUTH_FAIL {a['user']}: {e}")
            ok = False
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
