#!/usr/bin/env python3
"""Shared claim registry — 2 bot song song khong trung PDF / phieukhamId."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAIM_DIR = ROOT / "pipeline" / "work" / "locks" / "claims"
STALE_SEC = 45 * 60  # 45 min — bot chet thi claim het han


def _safe_key(key: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(key or ""))[:120]
    return s or "x"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import sys

        if sys.platform.startswith("win"):
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            SYNCHRONIZE = 0x00100000
            handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _read_claim(path: Path) -> tuple[int, str, float]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        pid = int((lines[0] if lines else "0").strip() or "0")
        owner = (lines[1] if len(lines) > 1 else "").strip()
        ts = float((lines[2] if len(lines) > 2 else "0").strip() or "0")
        return pid, owner, ts
    except Exception:
        return 0, "", 0.0


def try_claim(kind: str, key: str, owner: str) -> bool:
    """Return True if this owner may process kind:key (pdf / pid)."""
    if not key or not owner:
        return False
    CLAIM_DIR.mkdir(parents=True, exist_ok=True)
    path = CLAIM_DIR / f"{kind}_{_safe_key(key)}.claim"
    me = os.getpid()
    now = time.time()
    if path.exists():
        old_pid, old_owner, old_ts = _read_claim(path)
        age = now - (old_ts or path.stat().st_mtime)
        if old_owner == owner or old_pid == me:
            path.write_text(f"{me}\n{owner}\n{now}\n", encoding="utf-8")
            return True
        if _pid_alive(old_pid) and age < STALE_SEC:
            return False
    path.write_text(f"{me}\n{owner}\n{now}\n", encoding="utf-8")
    return True


def release_claim(kind: str, key: str, owner: str) -> None:
    path = CLAIM_DIR / f"{kind}_{_safe_key(key)}.claim"
    if not path.exists():
        return
    try:
        _, cur_owner, _ = _read_claim(path)
        if cur_owner == owner:
            path.unlink(missing_ok=True)
    except Exception:
        pass


def release_owner(owner: str) -> int:
    """Drop all claims held by owner (bot role tag)."""
    if not owner or not CLAIM_DIR.exists():
        return 0
    n = 0
    for p in CLAIM_DIR.glob("*.claim"):
        try:
            _, cur_owner, _ = _read_claim(p)
            if cur_owner == owner:
                p.unlink(missing_ok=True)
                n += 1
        except Exception:
            pass
    return n


def claim_owner(bot_role: str) -> str:
    return f"{bot_role}:{os.getpid()}"


class claim_scope:
    """Context manager: auto-release claim on continue/return/exception."""

    def __init__(self, kind: str, key: str, owner: str):
        self.kind = kind
        self.key = key
        self.owner = owner
        self.acquired = False

    def __enter__(self) -> bool:
        self.acquired = try_claim(self.kind, self.key, self.owner)
        return self.acquired

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.acquired:
            release_claim(self.kind, self.key, self.owner)
        return False
