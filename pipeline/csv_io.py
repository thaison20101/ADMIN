#!/usr/bin/env python3
"""Robust CSV text open for Windows ledgers (mixed utf-8 / cp1258 / latin-1)."""

from __future__ import annotations

import io
from pathlib import Path


def decode_csv_bytes(raw: bytes) -> tuple[str, str]:
    """Return (text, encoding_used). Never raises on bad bytes."""
    for enc in ("utf-8-sig", "utf-8", "cp1258", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def open_csv_read(path: Path, newline: str = ""):
    """Open CSV for DictReader; tolerate mixed encodings on may A cases.csv."""
    raw = path.read_bytes()
    text, _enc = decode_csv_bytes(raw)
    return io.StringIO(text, newline=newline)
