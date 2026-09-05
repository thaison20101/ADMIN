#!/usr/bin/env python3
"""SSL context for Medinet HTTPS (clinic PCs often have SSL-inspect / self-signed MITM)."""

from __future__ import annotations

import os
import ssl
from functools import lru_cache


def _want_verify() -> bool:
    """Default OFF: corporate/self-signed chain breaks urllib on may A.

    Enable strict verify with:
      set MEDINET_SSL_VERIFY=1
    or config.local.json medinet.ssl_verify = true
    """
    env = (os.environ.get("MEDINET_SSL_VERIFY") or "").strip().lower()
    if env in {"1", "true", "yes", "on"}:
        return True
    if env in {"0", "false", "no", "off"}:
        return False
    try:
        from pathlib import Path
        import json

        root = Path(__file__).resolve().parents[1]
        for name in ("config.local.json", "config.example.json"):
            p = root / "pipeline" / name
            if not p.exists():
                continue
            cfg = json.loads(p.read_text(encoding="utf-8-sig"))
            med = cfg.get("medinet") or {}
            if "ssl_verify" in med:
                return bool(med["ssl_verify"])
    except Exception:
        pass
    return False


@lru_cache(maxsize=1)
def medinet_ssl_context() -> ssl.SSLContext:
    if _want_verify():
        return ssl.create_default_context()
    ctx = ssl._create_unverified_context()  # noqa: S323 - intentional for MITM proxy
    return ctx


def urlopen(req, timeout: float = 60):
    """urllib.request.urlopen with Medinet SSL policy."""
    import urllib.request

    return urllib.request.urlopen(req, timeout=timeout, context=medinet_ssl_context())
