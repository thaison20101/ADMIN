#!/usr/bin/env python3
"""Resolve Google Drive pipeline paths the same way on every PC.

Discovers:
  <DriveLetter>/(Drive của tôi|My Drive|...)/PKDK_Thuankieu_Pipeline
  <DriveLetter>/(...)/build for Supper Data

Creates standard folders: INBOX_CLS, MISSING, ERROR, PROCESSED.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = Path(__file__).resolve().parent / "config.local.json"
EXAMPLE_CONFIG = Path(__file__).resolve().parent / "config.example.json"

PIPELINE_NAME = "PKDK_Thuankieu_Pipeline"
BUILD_NAME = "build for Supper Data"
DRIVE_MIDS = (
    "Drive của tôi",
    "Drive của Tôi",
    "My Drive",
    "Drive cua toi",
)
DRIVE_LETTERS = ("G:", "H:", "D:", "E:", "F:")
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


def _load_cfg() -> dict:
    for p in (LOCAL_CONFIG, EXAMPLE_CONFIG):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
    return {}


def discover_pipeline_root(cfg: dict | None = None) -> Path:
    cfg = cfg if cfg is not None else _load_cfg()
    raw = str((cfg.get("drive") or {}).get("local_sync_root") or "").strip()
    cands: list[Path] = []
    if raw:
        cands.append(Path(raw))
    for letter in DRIVE_LETTERS:
        for mid in DRIVE_MIDS:
            cands.append(Path(f"{letter}/{mid}/{PIPELINE_NAME}"))
    cands.append(ROOT / PIPELINE_NAME)
    for p in _unique(cands):
        try:
            if p.exists() and p.is_dir():
                return p
        except Exception:
            continue
    # Prefer creating under first existing Drive mid, else G:/Drive của tôi
    for letter in DRIVE_LETTERS:
        for mid in DRIVE_MIDS:
            base = Path(f"{letter}/{mid}")
            try:
                if base.exists():
                    dest = base / PIPELINE_NAME
                    dest.mkdir(parents=True, exist_ok=True)
                    return dest
            except Exception:
                continue
    dest = Path(f"G:/{DRIVE_MIDS[0]}/{PIPELINE_NAME}")
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def discover_build_root(cfg: dict | None = None) -> Path:
    cfg = cfg if cfg is not None else _load_cfg()
    raw = str((cfg.get("drive") or {}).get("build_root") or "").strip()
    cands: list[Path] = []
    if raw:
        cands.append(Path(raw))
    for letter in DRIVE_LETTERS:
        for mid in DRIVE_MIDS:
            cands.append(Path(f"{letter}/{mid}/{BUILD_NAME}"))
    cands.append(ROOT / "pipeline" / "work" / "build")
    for p in _unique(cands):
        try:
            if p.exists() and p.is_dir():
                return p
        except Exception:
            continue
    for letter in DRIVE_LETTERS:
        for mid in DRIVE_MIDS:
            base = Path(f"{letter}/{mid}")
            try:
                if base.exists():
                    dest = base / BUILD_NAME
                    dest.mkdir(parents=True, exist_ok=True)
                    return dest
            except Exception:
                continue
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
    return {
        "pipeline_root": str(pipeline),
        "build_root": str(build),
        "config": str(cfg_path),
        "pdf_counts": counts,
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
        print("OK: folders INBOX_CLS / MISSING / ERROR / PROCESSED ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
