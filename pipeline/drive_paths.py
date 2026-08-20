#!/usr/bin/env python3
"""Resolve Google Drive pipeline paths — may A only (G:\\Drive của tôi\\...).

PDF folders: G:\\Drive của tôi\\PKDK_Thuankieu_Pipeline
Logs/excel:  C:\\Users\\thais\\ADMIN\\pipeline\\work\\build  (never write to G:)

Khong quet D: / H: / mirror may B. Chi G:.
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
STD_FOLDERS = ("INBOX_CLS", "MISSING", "ERROR", "PROCESSED")
LOCAL_BUILD = ROOT / "pipeline" / "work" / "build"

# May A — duy nhat
PINNED_PIPELINE = Path(r"G:/Drive của tôi/PKDK_Thuankieu_Pipeline")
G_PIPELINE_VARIANTS = (
    PINNED_PIPELINE,
    Path(r"G:/Drive cua toi/PKDK_Thuankieu_Pipeline"),
    Path(r"G:/My Drive/PKDK_Thuankieu_Pipeline"),
    Path(r"G:/PKDK_Thuankieu_Pipeline"),
)


def is_non_g_pipeline(path: Path | str) -> bool:
    """True for D:\\PKDK mirror (may B) — never process."""
    u = str(path).replace("/", "\\").upper()
    return u.startswith("D:") and "PKDK" in u.replace(" ", "")


def is_forbidden_d_pipeline(path: Path | str) -> bool:
    return is_non_g_pipeline(path)


def require_g_on_windows(path: Path | str) -> bool:
    """On may A, pipeline PDFs must live under G:."""
    if not sys.platform.startswith("win"):
        return True
    return str(path).replace("/", "\\").upper().startswith("G:")


def g_pipeline_live() -> Path | None:
    """Return G: pipeline folder if Google Drive Desktop has it mounted."""
    for pinned in G_PIPELINE_VARIANTS:
        try:
            if pinned.exists() and pinned.is_dir():
                return pinned
        except Exception:
            continue
    return None


def local_work_build() -> Path:
    """Excel / heartbeat / snapshots — ALWAYS under ADMIN repo (never G:)."""
    dest = LOCAL_BUILD
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("logs", "excel_preview", "missing_or_updated", "cases_snapshot"):
        (dest / name).mkdir(parents=True, exist_ok=True)
    return dest


def _load_cfg() -> dict:
    for p in (LOCAL_CONFIG, EXAMPLE_CONFIG):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
    return {}


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


def resolve_g_sync(cfg: dict | None = None) -> Path:
    """PDF sync root: live G: if mounted, else pinned G: path.

    Never returns ADMIN repo, D:, or any non-G path on Windows.
    Callers on Windows must abort when g_pipeline_live() is None.
    """
    live = g_pipeline_live()
    if live is not None:
        return live

    cfg = cfg if cfg is not None else _load_cfg()
    raw = str((cfg.get("drive") or {}).get("local_sync_root") or "").strip()
    if raw:
        u = raw.replace("/", "\\").upper()
        # Only accept an existing G: path — refuse ADMIN / D: / C:
        if u.startswith("G:") and not is_non_g_pipeline(raw):
            return Path(raw)

    # Dev/CI without G: — local folder only (not D:, not used on Windows prod)
    if not sys.platform.startswith("win"):
        dest = ROOT / PIPELINE_NAME
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    # Windows + G: unmounted: pinned path for abort messaging only.
    # NEVER return ROOT / ADMIN — that caused sync=C:\Users\thais\ADMIN.
    return PINNED_PIPELINE


def discover_pipeline_root(cfg: dict | None = None) -> Path:
    """Always G:\\Drive của tôi\\PKDK_Thuankieu_Pipeline. Never D: / ADMIN / may B."""
    return resolve_g_sync(cfg)


def abort_if_not_g_live() -> str | None:
    """Return abort reason on Windows when G: pipeline is not live; else None."""
    if not sys.platform.startswith("win"):
        return None
    if g_pipeline_live() is None:
        return "g_drive_missing"
    return None


def discover_build_root(cfg: dict | None = None) -> Path:
    """Logs/excel — ALWAYS under ADMIN repo pipeline/work/build (never G:)."""
    del cfg
    return local_work_build()


def ensure_standard_folders(pipeline: Path, build: Path) -> dict[str, Path]:
    """Create folder layout. Never mkdir on G: when Drive is unmounted."""
    folders = {}
    can_touch_pipeline = True
    if sys.platform.startswith("win"):
        # Only create PDF folders when G: is actually live
        can_touch_pipeline = g_pipeline_live() is not None and str(pipeline).replace("/", "\\").upper().startswith("G:")
    if can_touch_pipeline:
        for name in STD_FOLDERS:
            p = pipeline / name
            try:
                p.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"WARN mkdir {p}: {e}")
            folders[name] = p
    else:
        for name in STD_FOLDERS:
            folders[name] = pipeline / name
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
    # Never persist ADMIN repo / D: / non-G as sync root on Windows
    if sys.platform.startswith("win"):
        if is_non_g_pipeline(pipeline) or not str(pipeline).replace("/", "\\").upper().startswith("G:"):
            print("WARN: refuse non-G: path; forcing G:\\Drive cua toi\\PKDK_Thuankieu_Pipeline")
            pipeline = PINNED_PIPELINE
        # Prefer live G: if mounted
        live = g_pipeline_live()
        if live is not None:
            pipeline = live
    drive["local_sync_root"] = str(pipeline).replace("\\", "/")
    drive["build_root"] = str(local_work_build()).replace("\\", "/")
    drive.setdefault("inbox_folder", "INBOX_CLS")
    drive.setdefault("processed_folder", "PROCESSED")
    drive.setdefault("error_folder", "ERROR")
    drive.setdefault("missing_folder", "MISSING")
    drive["root_folder_name"] = PIPELINE_NAME
    LOCAL_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return LOCAL_CONFIG


def sync_drive_layout(cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else _load_cfg()
    pipeline = discover_pipeline_root(cfg)
    build = discover_build_root(cfg)
    folders = ensure_standard_folders(pipeline, build)
    cfg_path = write_resolved_into_config(pipeline, build)
    counts = {}
    for name in STD_FOLDERS:
        p = folders[name]
        counts[name] = len(list(p.rglob("*.pdf"))) if p.exists() else 0
    on_g = str(pipeline).replace("/", "\\").upper().startswith("G:")
    return {
        "pipeline_root": str(pipeline),
        "build_root": str(build),
        "config": str(cfg_path),
        "pdf_counts": counts,
        # Dev/CI only — never a Windows prod fallback to ADMIN
        "using_local_fallback": (
            (not sys.platform.startswith("win"))
            and (not on_g)
            and (PIPELINE_NAME in str(pipeline))
        ),
        "hint": (
            ""
            if on_g and _pdf_count(pipeline) > 0
            else (
                "MO GOOGLE DRIVE DESKTOP tren may A, doi G:\\Drive cua toi sync xong roi chay lai."
                if sys.platform.startswith("win")
                else ""
            )
        ),
    }


def _first_existing_dir(cands: list[Path]) -> Path | None:
    for p in cands:
        try:
            if p.exists() and p.is_dir():
                return p
        except Exception:
            continue
    return None


def _best_pipeline_dir(cands: list[Path]) -> Path | None:
    existing = [p for p in cands if not is_non_g_pipeline(p)]
    existing = [p for p in existing if p.exists() and p.is_dir()]
    if not existing:
        return None
    scored = [(_pdf_count(p), p) for p in existing]
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[0][1]


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="May A: G:\\Drive cua toi\\PKDK_Thuankieu_Pipeline only")
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
            print("OK: may A G: only — INBOX_CLS / MISSING / ERROR / PROCESSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
