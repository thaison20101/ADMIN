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


# Medinet / WAF silently drops default Python-urllib User-Agent (read timeout).
# Browser UA works (~2s). Inject on every HTTPS call through this wrapper.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
BROWSER_ORIGIN = "https://quanlyskcd.medinet.org.vn"


def medinet_http_headers(extra: dict | None = None) -> dict:
    """Headers that Medinet accepts (not bare Python-urllib)."""
    h = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json, text/plain, */*",
        "Origin": BROWSER_ORIGIN,
        "Referer": BROWSER_ORIGIN + "/",
    }
    if extra:
        h.update(extra)
    return h


def _ensure_browser_headers(req) -> None:
    """Mutate Request so WAF does not hang on Python-urllib UA."""
    import urllib.request

    if not isinstance(req, urllib.request.Request):
        return
    # urllib stores headers with title-case; get_header looks up 'User-agent'
    if not req.has_header("User-agent"):
        req.add_header("User-Agent", BROWSER_UA)
    if not req.has_header("Accept"):
        req.add_header("Accept", "application/json, text/plain, */*")
    if not req.has_header("Origin"):
        req.add_header("Origin", BROWSER_ORIGIN)
    if not req.has_header("Referer"):
        req.add_header("Referer", BROWSER_ORIGIN + "/")


def urlopen(req, timeout: float = 60):
    """urllib.request.urlopen with Medinet SSL policy + browser UA."""
    import urllib.request

    install_medinet_https_opener()
    _ensure_browser_headers(req)
    return urllib.request.urlopen(req, timeout=timeout, context=medinet_ssl_context())


def probe_connectivity(host: str = "be-qlskcd.medinet.org.vn", port: int = 443) -> None:
    """Print DNS + TCP reachability (helps separate timeout vs bad password)."""
    import socket

    print(f"probe: DNS/TCP {host}:{port} ...", flush=True)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = sorted({i[4][0] for i in infos})
        print(f"probe: DNS OK ips={ips[:4]}", flush=True)
    except Exception as e:
        print(f"probe: DNS FAIL {e}", flush=True)
        return
    try:
        s = socket.create_connection((ips[0], port), timeout=15)
        s.close()
        print(f"probe: TCP OK {ips[0]}:{port}", flush=True)
    except Exception as e:
        print(f"probe: TCP FAIL {ips[0]}:{port} {e}", flush=True)


def probe_auth() -> int:
    """Exit 0 if Medinet auth works with current SSL policy; else 2."""
    reset_ssl_cache()
    install_medinet_https_opener()
    print(f"probe: MEDINET_SSL_VERIFY={os.environ.get('MEDINET_SSL_VERIFY')!r} want_verify={_want_verify()}")
    print(f"probe: monkeypatch={_monkey_patched} file={__file__}")
    probe_connectivity()
    try:
        from medinet_api import authenticate
        from medinet_creds import get_medinet_accounts

        accts = get_medinet_accounts({})
        print(
            f"probe: trying login user={accts[0]['user']} pass_prefix={accts[0]['password'][:4]}***",
            flush=True,
        )
        tok = authenticate(accts[0]["user"], accts[0]["password"])
        print(f"probe: auth OK account={accts[0]['id']} token_len={len(tok or '')}")
        return 0
    except TimeoutError as e:
        print(f"probe: AUTH TIMEOUT (KHONG phai sai pass): {e}")
        print("probe: Tip da gui User-Agent Chrome. Neu van timeout: mang/proxy.")
        print("probe: Mo https://quanlyskcd.medinet.org.vn - neu web OK ma Python van treo: git pull tip moi.")
        return 2
    except Exception as e:
        print(f"probe: AUTH FAIL: {e}")
        err = str(e).upper()
        if "CERTIFICATE" in err or "SSL" in err:
            print("probe: SSL still failing - git pull cursor/hourly-flash-fix-df0f roi chay lai")
        elif "AUTH FAILED" in err or "SAI USER" in err:
            print("probe: SAI PASS - doi lai Qlskcd@2026 tren web Medinet cho pkdkthuankieu")
        return 2


# Apply as soon as module is imported (hourly_sync / medinet_api / phase_b)
apply_ssl_monkeypatch()


if __name__ == "__main__":
    raise SystemExit(probe_auth())
