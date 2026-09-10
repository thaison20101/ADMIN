#!/usr/bin/env python3
"""Ensure pipeline/config.local.json exists with safe defaults for one-shot/hourly runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = Path(__file__).resolve().parent / "config.local.json"
EXAMPLE = Path(__file__).resolve().parent / "config.example.json"

# ASCII-only path literals; drive_paths resolves real Drive folder names.
DEFAULT_SYNC = r"G:/Drive cua toi/PKDK_Thuankieu_Pipeline"
# Excel/heartbeat MUST stay local - writing them to G: unmounts Drive (WinError 3).
DEFAULT_BUILD = str((Path(__file__).resolve().parent / "work" / "build")).replace("\\", "/")


def main() -> int:
    if not CFG.exists():
        if EXAMPLE.exists():
            CFG.write_text(EXAMPLE.read_text(encoding="utf-8-sig"), encoding="utf-8")
        else:
            CFG.write_text("{}", encoding="utf-8")

    cfg = json.loads(CFG.read_text(encoding="utf-8-sig"))
    drive = cfg.setdefault("drive", {})
    # Keep existing paths if already set (may contain Vietnamese folder names)
    drive.setdefault("local_sync_root", DEFAULT_SYNC)
    drive.setdefault("inbox_folder", "INBOX_CLS")
    drive.setdefault("processed_folder", "PROCESSED")
    drive.setdefault("error_folder", "ERROR")
    drive.setdefault("missing_folder", "MISSING")
    # Always local logs - never G:\build for Supper Data (that unmounts Drive)
    drive["build_root"] = DEFAULT_BUILD
    # May A only: luon G:\Drive cua toi (khong may B / o D:)
    g_pipe = Path(r"G:/Drive của tôi/PKDK_Thuankieu_Pipeline")
    old_sync = str(drive.get("local_sync_root") or "")
    if old_sync and not old_sync.replace("/", "\\").upper().startswith("G:"):
        print("WARN: config cu khong phai G: - da ghi de bang duong dan may A")
    drive["local_sync_root"] = str(g_pipe).replace("\\", "/")

    med = cfg.setdefault("medinet", {})
    # Always: 01/07/2026 -> today (rolling; empty date_to = hôm nay)
    med["date_from"] = "01/07/2026"
    med["date_to"] = ""  # empty = today in auto_cycle / rasoat / repair
    # May A self-signed MITM: force OFF unless operator sets MEDINET_SSL_VERIFY=1
    import os

    env_ssl = (os.environ.get("MEDINET_SSL_VERIFY") or "").strip().lower()
    if env_ssl in {"1", "true", "yes", "on"}:
        med["ssl_verify"] = True
        print("config: medinet.ssl_verify=true (MEDINET_SSL_VERIFY=1)")
    else:
        med["ssl_verify"] = False
        print("config: medinet.ssl_verify=false (may A self-signed OK)")
    # Rotate legacy defaults → current PKDK login (config.local is gitignored)
    old_users = {"", "pkdkthuankieu"}
    old_passes = {"", "P@ssw0rd"}
    if str(med.get("username") or "").strip() in old_users:
        med["username"] = "pkdk_Thuankieu"
    if str(med.get("password") or "").strip() in old_passes:
        med["password"] = "pkdk_Thuankieu#2026"

    rules = cfg.setdefault("import_rules", {})
    rules["enabled"] = True
    rules["auto_hourly"] = True
    # Enough headroom for hourly NEW inbox imports + full archive recheck
    cur = int(rules.get("max_imports_per_run") or 0)
    rules["max_imports_per_run"] = max(cur, 20000)
    rules["max_incomplete_per_run"] = max(int(rules.get("max_incomplete_per_run") or 0), 20000)

    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from medinet_ssl import reset_ssl_cache

        reset_ssl_cache()
    except Exception:
        pass

    # Auto-discover real Drive paths + create standard folders (same on every PC)
    try:
        from drive_paths import sync_drive_layout

        summary = sync_drive_layout(cfg)
        sync_root = summary["pipeline_root"]
        build_root = summary["build_root"]
    except Exception as e:
        # Never fall back to ADMIN as sync - keep pinned G: from config write above
        sync_root = drive.get("local_sync_root") or DEFAULT_SYNC
        build_root = drive.get("build_root") or DEFAULT_BUILD
        print(f"WARN drive_paths: {e}")
        if str(sync_root).replace("/", "\\").upper().startswith(("C:", "D:")):
            sync_root = DEFAULT_SYNC
            print("WARN: refuse ADMIN/D fallback; keep G: pin")

    from datetime import date

    print(
        "config OK",
        sync_root,
        "build=",
        build_root,
        "date_from=01/07/2026",
        f"date_to=today({date.today().strftime('%d/%m/%Y')})",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
