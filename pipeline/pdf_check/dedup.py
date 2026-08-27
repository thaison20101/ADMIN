"""Detect duplicate PDF names (and optional content hash) across folders."""

from __future__ import annotations

import hashlib
import shutil
import time
from collections import defaultdict
from pathlib import Path

# Subfolders under PKDK_Thuankieu_Pipeline (flat PDF per folder).
PIPELINE_SUBFOLDERS = (
    "INBOX_CLS",
    "MISSING",
    "ERROR",
    "PROCESSED",
    "UNDER 18",
    "TK1",
    "TK2",
)


def sha256_file(path: Path, limit_mb: int = 32) -> str:
    h = hashlib.sha256()
    max_bytes = limit_mb * 1024 * 1024
    total = 0
    try:
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
        return h.hexdigest()
    except OSError:
        return ""


def mark_duplicates(
    scan_rows: list[dict],
    *,
    compute_hash: bool = False,
) -> list[dict]:
    """Annotate each scan row with dup fields; returns new list of dicts."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    out: list[dict] = []
    for r in scan_rows:
        row = dict(r)
        key = str(row.get("file_name") or "").lower()
        by_name[key].append(row)
        out.append(row)

    for _key, group in by_name.items():
        folders = sorted({str(g.get("folder") or "") for g in group})
        is_dup = len(group) >= 2
        dup_folders = "|".join(folders) if is_dup else ""
        for g in group:
            g["is_dup_name"] = "YES" if is_dup else "NO"
            g["dup_folders"] = dup_folders if is_dup else ""
            g["dup_count"] = len(group) if is_dup else 1

    if compute_hash:
        by_hash: dict[str, list[dict]] = defaultdict(list)
        for row in out:
            path = row.get("path")
            digest = sha256_file(Path(path)) if path else ""
            row["file_hash"] = digest
            if digest:
                by_hash[digest].append(row)
        for _digest, group in by_hash.items():
            if len(group) < 2:
                for g in group:
                    g["same_hash_dup"] = "NO"
                    g.setdefault("hash_dup_folders", "")
                continue
            folders = sorted({str(g.get("folder") or "") for g in group})
            label = "|".join(folders)
            for g in group:
                g["same_hash_dup"] = "YES"
                g["hash_dup_folders"] = label
        for row in out:
            row.setdefault("same_hash_dup", "NO")
            row.setdefault("hash_dup_folders", "")
            row.setdefault("file_hash", "")
    else:
        for row in out:
            row["same_hash_dup"] = "SKIP"
            row["hash_dup_folders"] = ""
            row["file_hash"] = ""

    return out


def _flat_pdf_exists(folder: Path, file_name: str) -> bool:
    p = folder / file_name
    try:
        return p.is_file()
    except OSError:
        return False


def inbox_duplicate_exists(sync_root: Path, file_name: str, *, exclude: Path | None = None) -> bool:
    """True if file_name exists in any pipeline subfolder (except exclude path)."""
    for sub in PIPELINE_SUBFOLDERS:
        p = sync_root / sub / file_name
        if exclude is not None:
            try:
                if p.resolve() == exclude.resolve():
                    continue
            except OSError:
                if str(p) == str(exclude):
                    continue
        if _flat_pdf_exists(sync_root / sub, file_name):
            return True
    return False


def hold_inbox_duplicate_at_root(
    pdf: Path,
    sync_root: Path,
    *,
    dry_run: bool = False,
) -> Path | None:
    """Move INBOX duplicate to pipeline root (same level as INBOX_CLS)."""
    if not pdf.exists():
        return None
    dest = sync_root / pdf.name
    if dest.exists():
        stem, suf = pdf.stem, pdf.suffix
        for i in range(1, 20):
            alt = sync_root / f"{stem}_dup{i}{suf}"
            if not alt.exists():
                dest = alt
                break
    if dry_run:
        return dest
    last_err = None
    for attempt in range(3):
        try:
            shutil.move(str(pdf), str(dest))
            return dest
        except OSError as e:
            last_err = e
            time.sleep(0.4 * (attempt + 1))
    raise OSError(f"hold_inbox_dup_root fail {pdf.name}: {last_err}")
