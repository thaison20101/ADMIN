"""Scan PDF files in pipeline folders (top-level flat, no deep rglob)."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_FOLDERS = (
    "INBOX_CLS",
    "MISSING",
    "ERROR",
    "PROCESSED",
    "TK1",
    "TK2",
    "UNDER 18",
)


def list_pdfs_in_folder(folder: Path) -> list[Path]:
    """List *.pdf directly under folder (flat scandir — avoid Drive hydrate)."""
    if not folder.exists():
        return []
    out: list[Path] = []
    try:
        with os.scandir(folder) as it:
            for ent in it:
                try:
                    if ent.is_file(follow_symlinks=False) and ent.name.lower().endswith(
                        ".pdf"
                    ):
                        out.append(Path(ent.path))
                except OSError:
                    continue
    except OSError:
        return []
    return sorted(out, key=lambda p: p.name.lower())


def scan_pipeline_pdfs(
    sync_root: Path,
    folders: tuple[str, ...] | list[str] | None = None,
) -> list[dict]:
    """Return [{folder, path, file_name}, ...] for each PDF found."""
    names = tuple(folders) if folders else DEFAULT_FOLDERS
    rows: list[dict] = []
    for name in names:
        d = sync_root / name
        for pdf in list_pdfs_in_folder(d):
            rows.append(
                {
                    "folder": name,
                    "path": pdf,
                    "file_name": pdf.name,
                }
            )
    return rows
