#!/usr/bin/env python3
"""SSL context for Medinet HTTPS (clinic PCs often have SSL-inspect / self-signed MITM).

Default: VERIFY OFF. May A always needs this. Strict only if MEDINET_SSL_VERIFY=1.

Also monkey-patches ssl._create_default_https_context so ANY urllib/https
call (even without our urlopen wrapper) skips verify on may A.
"""

from __future__ import annotations

import os
import ssl
import sys


def _want_verify() -> bool:
    """Default OFF. Only strict when MEDINET_SSL_VERIFY=1/true."""
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


_ctx: ssl.SSLContext | None = None
_logged = False
_opener_installed = False
_monkey_patched = False


def medinet_ssl_context() -> ssl.SSLContext:
    global _ctx, _logged
    verify = _want_verify()
    if _ctx is None:
        if verify:
            _ctx = ssl.create_default_context()
        else:
            _ctx = ssl._create_unverified_context()  # noqa: S323 - MITM proxy on may A
    if not _logged:
        _logged = True
        mode = "ON (strict)" if verify else "OFF (self-signed OK)"
        print(f"medinet_ssl: verify={mode}", file=sys.stderr, flush=True)
    return _ctx


def apply_ssl_monkeypatch() -> None:
    """Force Python default HTTPS context = Medinet policy (nuclear for may A)."""
    global _monkey_patched
    if _monkey_patched:
        return
    if _want_verify():
        _monkey_patched = True
        return

    def _unverified_https_context():
        return ssl._create_unverified_context()  # noqa: S323

    ssl._create_default_https_context = _unverified_https_context  # type: ignore[attr-defined]
    _monkey_patched = True


def reset_ssl_cache() -> None:
    """Call after ensure_config rewrites ssl_verify."""
    global _ctx, _logged, _opener_installed, _monkey_patched
    _ctx = None
    _logged = False
    _opener_installed = False
    _monkey_patched = False
    apply_ssl_monkeypatch()


def install_medinet_https_opener() -> None:
    """Belt-and-suspenders: default HTTPS handler uses Medinet SSL policy."""
    global _opener_installed
    apply_ssl_monkeypatch()
    if _opener_installed:
        return
    import urllib.request

    ctx = medinet_ssl_context()
    https = urllib.request.HTTPSHandler(context=ctx)
    opener = urllib.request.build_opener(https)
    urllib.request.install_opener(opener)
    _opener_installed = True


def urlopen(req, timeout: float = 60):
    """urllib.request.urlopen with Medinet SSL policy."""
    import urllib.request

    install_medinet_https_opener()
    return urllib.request.urlopen(req, timeout=timeout, context=medinet_ssl_context())


def probe_auth() -> int:
    """Exit 0 if Medinet auth works with current SSL policy; else 2."""
    reset_ssl_cache()
    install_medinet_https_opener()
    print(f"probe: MEDINET_SSL_VERIFY={os.environ.get('MEDINET_SSL_VERIFY')!r} want_verify={_want_verify()}")
    print(f"probe: monkeypatch={_monkey_patched} file={__file__}")
    try:
        from medinet_api import authenticate
        from medinet_creds import get_medinet_accounts

        accts = get_medinet_accounts({})
        tok = authenticate(accts[0]["user"], accts[0]["password"])
        print(f"probe: auth OK account={accts[0]['id']} token_len={len(tok or '')}")
        return 0
    except Exception as e:
        print(f"probe: AUTH FAIL: {e}")
        if "CERTIFICATE" in str(e).upper() or "SSL" in str(e).upper():
            print("probe: SSL still failing - git pull cursor/hourly-flash-fix-df0f roi chay lai")
        return 2


# Apply as soon as module is imported (hourly_sync / medinet_api / phase_b)
apply_ssl_monkeypatch()


if __name__ == "__main__":
    raise SystemExit(probe_auth())
