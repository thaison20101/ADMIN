"""Detect duplicate PDF names (and optional content hash) across folders."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path


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
