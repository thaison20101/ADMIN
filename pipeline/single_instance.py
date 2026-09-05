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


def acquire_lock(name: str = "auto_cycle", *, stale_hours: float = 2.5) -> Path | None:
    """Return lock path if acquired; None if another live instance holds it.

    Default stale_hours=2.5 matches hourly ExecutionTimeLimit (~2h): a hung
    bot must not block every later hourly tick for half a day.
    Dead PID or age >= stale_hours => reclaim.
    """
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
            alive = _pid_alive(old_pid)
            if alive and age_h < stale_hours:
                return None
            # Stale / dead owner — take over (log so hourly "flash" is diagnosable)
            reason = "dead_pid" if not alive else f"age_h={age_h:.2f}>={stale_hours}"
            try:
                sys.stderr.write(
                    f"LOCK_RECLAIM name={name} old_pid={old_pid} reason={reason}\n"
                )
            except Exception:
                pass
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


def merge_cases_rows(base: list[dict], updates: list[dict]) -> list[dict]:
    """Merge bot updates into ledger by case_key (parallel inbox+missing bots)."""
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for r in base:
        k = str(r.get("case_key") or "")
        if not k:
            continue
        if k not in by_key:
            order.append(k)
        by_key[k] = r
    for r in updates:
        k = str(r.get("case_key") or "")
        if not k:
            continue
        if k not in by_key:
            order.append(k)
        by_key[k] = r
    return [by_key[k] for k in order if k in by_key]


def save_cases_merged(cases_path, rows: list[dict], write_fn) -> None:
    """Atomic-ish save: re-read ledger, merge by case_key, write."""
    from pathlib import Path

    path = Path(cases_path)
    lock = acquire_lock("cases_csv", stale_hours=0.25)
    if lock is None:
        # Fallback: direct write (single bot)
        write_fn(path, rows)
        return
    try:
        from hourly_sync import read_cases

        current = read_cases(path)
        merged = merge_cases_rows(current, rows)
        write_fn(path, merged)
    finally:
        release_lock(lock)
