#!/usr/bin/env python3
"""Resolve Google Drive pipeline paths the same way on every PC.

Discovers:
  <DriveLetter>/(Drive của tôi|My Drive|...)/PKDK_Thuankieu_Pipeline
  <DriveLetter>/(...)/build for Supper Data
  Also: %USERPROFILE%\\Google Drive\\..., GoogleDrive\\...

Never mkdir on a missing drive letter (avoids WinError 3 on PCs without G:).
Creates standard folders: INBOX_CLS, MISSING, ERROR, PROCESSED — only under a
path that already exists or under local fallback.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = Path(__file__).resolve().parent / "config.local.json"
EXAMPLE_CONFIG = Path(__file__).resolve().parent / "config.example.json"

PIPELINE_NAME = "PKDK_Thuankieu_Pipeline"
BUILD_NAME = "build for Supper Data"
DRIVE_MIDS = (
    "My Drive",  # Google Drive Desktop (English) — phổ biến máy mới
    "Drive của tôi",
    "Drive của Tôi",
    "Drive cua toi",
)
DRIVE_LETTERS = ("G:", "H:", "D:", "E:", "F:", "I:", "J:")
STD_FOLDERS = ("INBOX_CLS", "MISSING", "ERROR", "PROCESSED")


def _unique(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p).replace("\\", "/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _drive_exists(letter: str) -> bool:
    """True only if Windows drive letter is mounted (e.g. G:)."""
    try:
        root = Path(f"{letter}/")
        return root.exists()
    except Exception:
        return False


def _load_cfg() -> dict:
    for p in (LOCAL_CONFIG, EXAMPLE_CONFIG):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
    return {}


def _user_drive_bases() -> list[Path]:
    """Common Google Drive Desktop locations under the user profile."""
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    bases: list[Path] = []
    for name in (
        "Google Drive",
        "GoogleDrive",
        "My Drive",
        "Drive của tôi",
        "Drive cua toi",
    ):
        bases.append(home / name)
    # Newer Google Drive Desktop often nests: Google Drive/My Drive
    for outer in ("Google Drive", "GoogleDrive"):
        for mid in DRIVE_MIDS:
            bases.append(home / outer / mid)
    return bases


def _pipeline_candidates(cfg: dict) -> list[Path]:
    raw = str((cfg.get("drive") or {}).get("local_sync_root") or "").strip()
    cands: list[Path] = []
    if raw:
        cands.append(Path(raw))
    for letter in DRIVE_LETTERS:
        if not _drive_exists(letter):
            continue
        for mid in DRIVE_MIDS:
            cands.append(Path(f"{letter}/{mid}/{PIPELINE_NAME}"))
            cands.append(Path(f"{letter}/{PIPELINE_NAME}"))
    for base in _user_drive_bases():
        cands.append(base / PIPELINE_NAME)
        for mid in DRIVE_MIDS:
            cands.append(base / mid / PIPELINE_NAME)
    cands.append(ROOT / PIPELINE_NAME)
    return _unique(cands)


def _build_candidates(cfg: dict) -> list[Path]:
    raw = str((cfg.get("drive") or {}).get("build_root") or "").strip()
    cands: list[Path] = []
    if raw:
        cands.append(Path(raw))
    for letter in DRIVE_LETTERS:
        if not _drive_exists(letter):
            continue
        for mid in DRIVE_MIDS:
            cands.append(Path(f"{letter}/{mid}/{BUILD_NAME}"))
            cands.append(Path(f"{letter}/{BUILD_NAME}"))
    for base in _user_drive_bases():
        cands.append(base / BUILD_NAME)
        for mid in DRIVE_MIDS:
            cands.append(base / mid / BUILD_NAME)
    cands.append(ROOT / "pipeline" / "work" / "build")
    return _unique(cands)


def _pdf_count(root: Path) -> int:
    n = 0
    try:
        if not root.exists():
            return 0
        for name in STD_FOLDERS:
            p = root / name
            if p.exists():
                n += sum(1 for _ in p.rglob("*.pdf"))
    except Exception:
        return n
    return n


def _best_pipeline_dir(cands: list[Path]) -> Path | None:
    """Prefer the tree that actually holds PDFs (D: empty mirror must not win)."""
    existing: list[Path] = []
    for p in cands:
        try:
            if p.exists() and p.is_dir():
                existing.append(p)
        except Exception:
            continue
    if not existing:
        return None
    scored = [( _pdf_count(p), p) for p in existing]
    scored.sort(key=lambda t: t[0], reverse=True)
    best_n, best = scored[0]
    if best_n == 0:
        return existing[0]
    return best


def _create_under_existing_base(name: str) -> Path | None:
    """Create <base>/<name> only when <base> already exists."""
    bases: list[Path] = []
    for letter in DRIVE_LETTERS:
        if not _drive_exists(letter):
            continue
        for mid in DRIVE_MIDS:
            bases.append(Path(f"{letter}/{mid}"))
        bases.append(Path(f"{letter}/"))
    bases.extend(_user_drive_bases())
    for base in _unique(bases):
        try:
            if not base.exists():
                continue
            dest = base / name
            dest.mkdir(parents=True, exist_ok=True)
            return dest
        except Exception:
            continue
    return None


def discover_pipeline_root(cfg: dict | None = None) -> Path:
    cfg = cfg if cfg is not None else _load_cfg()
    found = _best_pipeline_dir(_pipeline_candidates(cfg))
    if found:
        return found
    created = _create_under_existing_base(PIPELINE_NAME)
    if created:
        return created
    # Local fallback — never touch missing G:
    dest = ROOT / PIPELINE_NAME
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def discover_build_root(cfg: dict | None = None) -> Path:
    cfg = cfg if cfg is not None else _load_cfg()
    found = _first_existing_dir(_build_candidates(cfg))
    if found:
        return found
    created = _create_under_existing_base(BUILD_NAME)
    if created:
        return created
    dest = ROOT / "pipeline" / "work" / "build"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def ensure_standard_folders(pipeline: Path, build: Path) -> dict[str, Path]:
    folders = {}
    for name in STD_FOLDERS:
        p = pipeline / name
        p.mkdir(parents=True, exist_ok=True)
        folders[name] = p
    for name in ("logs", "excel_preview", "missing_or_updated", "cases_snapshot"):
        p = build / name
        p.mkdir(parents=True, exist_ok=True)
        folders[f"build_{name}"] = p
    return folders


def write_resolved_into_config(pipeline: Path, build: Path) -> Path:
    if LOCAL_CONFIG.exists():
        cfg = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8-sig"))
    elif EXAMPLE_CONFIG.exists():
        cfg = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8-sig"))
    else:
        cfg = {}
    drive = cfg.setdefault("drive", {})
    drive["local_sync_root"] = str(pipeline).replace("\\", "/")
    drive["build_root"] = str(build).replace("\\", "/")
    drive.setdefault("inbox_folder", "INBOX_CLS")
    drive.setdefault("processed_folder", "PROCESSED")
    drive.setdefault("error_folder", "ERROR")
    drive.setdefault("missing_folder", "MISSING")
    drive["root_folder_name"] = PIPELINE_NAME
    LOCAL_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return LOCAL_CONFIG


def sync_drive_layout(cfg: dict | None = None) -> dict:
    """Discover + create + write config.local.json. Returns summary dict."""
    cfg = cfg if cfg is not None else _load_cfg()
    pipeline = discover_pipeline_root(cfg)
    build = discover_build_root(cfg)
    folders = ensure_standard_folders(pipeline, build)
    cfg_path = write_resolved_into_config(pipeline, build)
    counts = {}
    for name in STD_FOLDERS:
        p = folders[name]
        counts[name] = len(list(p.rglob("*.pdf"))) if p.exists() else 0
    on_drive = any(
        str(pipeline).upper().startswith(f"{L}/") or str(pipeline).upper().startswith(f"{L}\\")
        for L in DRIVE_LETTERS
    ) or ("google" in str(pipeline).lower()) or ("drive" in str(pipeline).lower() and "pipeline" not in str(pipeline.parent).lower())
    return {
        "pipeline_root": str(pipeline),
        "build_root": str(build),
        "config": str(cfg_path),
        "pdf_counts": counts,
        "using_local_fallback": str(ROOT) in str(pipeline),
        "hint": (
            ""
            if not (str(ROOT) in str(pipeline))
            else "CHUA THAY GOOGLE DRIVE — cai Google Drive Desktop, dang nhap, doi sync xong roi chay lai."
        ),
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Dong bo / resolve Google Drive folders")
    ap.add_argument("--json", action="store_true", help="Print summary as JSON")
    args = ap.parse_args()

    summary = sync_drive_layout()
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"PIPELINE: {summary['pipeline_root']}")
        print(f"BUILD   : {summary['build_root']}")
        print(f"CONFIG  : {summary['config']}")
        for k, n in (summary.get("pdf_counts") or {}).items():
            print(f"  {k}: {n} pdf")
        if summary.get("hint"):
            print(f"WARN: {summary['hint']}")
        else:
            print("OK: folders INBOX_CLS / MISSING / ERROR / PROCESSED ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
