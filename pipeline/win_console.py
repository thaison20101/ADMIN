#!/usr/bin/env python3
"""Make stdout/stderr safe on Windows consoles (cp1252/charmap)."""

from __future__ import annotations

import sys


def setup_utf8_stdio() -> None:
    """Avoid UnicodeEncodeError when printing Vietnamese paths on Windows."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def safe_print(*args, **kwargs) -> None:
    kwargs.setdefault("flush", True)
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(a) for a in args)
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        data = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(data, **kwargs)
