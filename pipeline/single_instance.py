#!/usr/bin/env python3
"""Single-instance lock for pipeline runs (prevent 2 bots corrupting cases.csv)."""

from __future__ import annotations

import atexit
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_DIR = ROOT / "pipeline" / "work" / "locks"
DEFAULT_LOCK = LOCK_DIR / "auto_cycle.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
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


def acquire_lock(name: str = "auto_cycle", *, stale_hours: float = 12.0) -> Path | None:
    """Return lock path if acquired; None if another live instance holds it."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCK_DIR / f"{name}.lock"
    me = os.getpid()
    now = time.time()
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            old_pid = int((text.splitlines() or ["0"])[0].strip() or "0")
            age_h = (now - path.stat().st_mtime) / 3600.0
            if old_pid == me:
                return path
            if _pid_alive(old_pid) and age_h < stale_hours:
                return None
            # Stale / dead owner — take over
        except Exception:
            pass
    path.write_text(
        f"{me}\nstarted={time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8",
    )

    def _release() -> None:
        try:
            if path.exists():
                cur = path.read_text(encoding="utf-8", errors="replace").splitlines()
                if cur and cur[0].strip() == str(me):
                    path.unlink(missing_ok=True)
        except Exception:
            pass

    atexit.register(_release)
    return path


def release_lock(path: Path | None) -> None:
    if not path:
        return
    try:
        me = str(os.getpid())
        if path.exists():
            cur = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if cur and cur[0].strip() == me:
                path.unlink(missing_ok=True)
    except Exception:
        pass
