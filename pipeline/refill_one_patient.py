#!/usr/bin/env python3
"""Force re-fill one patient CLS from PDF (bypass gap-only skip).

Default: VONG QUOC CHU / 079087013411 — form still missing MCHC/RDW.

Usage (may A):
  cd C:\\Users\\thais\\ADMIN
  python .\\pipeline\\refill_one_patient.py
  python .\\pipeline\\refill_one_patient.py --cccd 079087013411 --pdf \"G:\\...\\file.pdf\"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPE = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPE))

from drive_paths import (  # noqa: E402
    discover_build_root,
    discover_pipeline_root,
    ensure_standard_folders,
)
from medinet_api import (  # noqa: E402
    authenticate,
    cls_missing_lab_fields,
    insert_cls,
    labs_to_form_payload,
    load_cls_view,
    verify_cls_saved,
)
from medinet_creds import get_medinet_accounts  # noqa: E402
from medinet_ssl import install_medinet_https_opener  # noqa: E402
from pdf_extract import extract_pdf  # noqa: E402
from phase_b_preview import load_or_fetch_merged_unit_index  # noqa: E402
from tthc_match import resolve_tthc_matches  # noqa: E402


def _today_dmy() -> str:
    return date.today().strftime("%d/%m/%Y")


def _iter_pdfs(folder: Path):
    if not folder.exists():
        return
    try:
        yield from folder.rglob("*.pdf")
        yield from folder.rglob("*.PDF")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN rglob {folder}: {exc}", flush=True)


def _find_pdf(cccd: str, name_hint: str, explicit: Path | None) -> Path | None:
    if explicit and explicit.is_file():
        return explicit
    sync = discover_pipeline_root()
    build = discover_build_root()
    folders = ensure_standard_folders(sync, build)
    # Prefer ERROR / CCCD / MISSING / PROCESSED then TK
    order = [
        "ERROR",
        "CCCD",
        "MISSING",
        "PROCESSED",
        "TK1",
        "TK2",
        "INBOX_CLS",
        "UNDER 18",
    ]
    needles = [cccd]
    if name_hint:
        needles.append(name_hint.upper().replace("Ò", "O").replace("Ố", "O"))
        needles.append(name_hint.upper())

    best: Path | None = None
    best_mtime = -1.0
    seen: set[str] = set()
    for name in order:
        root = folders.get(name) or (sync / name)
        for pdf in _iter_pdfs(root):
            key = str(pdf).lower()
            if key in seen:
                continue
            seen.add(key)
            u = str(pdf).upper()
            if not any(n and n.upper() in u for n in needles if n):
                # Still try if filename has digits of CCCD
                if cccd not in str(pdf):
                    continue
            try:
                data = extract_pdf(pdf)
            except Exception:
                continue
            if (data.get("cccd") or "").strip() != cccd:
                continue
            try:
                mt = pdf.stat().st_mtime
            except Exception:
                mt = 0.0
            if mt >= best_mtime:
                best_mtime = mt
                best = pdf
    return best


def _lab_web(labs: dict, key: str):
    item = labs.get(key) or {}
    if isinstance(item, dict):
        return item.get("value_web") or item.get("value_raw")
    return item


def main() -> int:
    import os

    os.environ["MEDINET_SSL_VERIFY"] = "0"
    install_medinet_https_opener()
    ap = argparse.ArgumentParser(description="Force refill one CLS form from PDF")
    ap.add_argument("--cccd", default="079087013411")
    ap.add_argument("--name", default="VONG QUOC CHU")
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--date-from", default="01/07/2026")
    ap.add_argument("--date-to", default="")
    args = ap.parse_args()

    cccd = args.cccd.strip()
    date_to = (args.date_to or "").strip() or _today_dmy()
    build = discover_build_root()
    build.mkdir(parents=True, exist_ok=True)

    print(f"=== REFILL FORCE {args.name} / {cccd} ===", flush=True)

    pdf = _find_pdf(cccd, args.name, args.pdf)
    if pdf is None:
        print("FAIL: khong tim thay PDF tren G: cho CCCD nay", flush=True)
        return 2
    print(f"PDF: {pdf}", flush=True)

    data = extract_pdf(pdf)
    labs = data.get("labs") or {}
    print(
        f"PARSE mchc={_lab_web(labs, 'MCHC')!r} rdw={_lab_web(labs, 'RDW')!r} "
        f"duong={_lab_web(labs, 'Glucose')!r} "
        f"lucdoi={_lab_web(labs, 'Glucose_fasting')!r} "
        f"ure={_lab_web(labs, 'Urea')!r}",
        flush=True,
    )
    if not _lab_web(labs, "MCHC") or not _lab_web(labs, "RDW"):
        print(
            "WARN: PDF parse chua ra MCHC/RDW — kiem tra text PDF (MCHC303/RDW11.4)",
            flush=True,
        )

    accounts = get_medinet_accounts()
    cache_dir = ROOT / "pipeline" / "work" / "index_cache"
    print("Loading unit index (force refresh)...", flush=True)
    index = load_or_fetch_merged_unit_index(
        accounts,
        args.date_from,
        date_to,
        cache_dir=cache_dir,
        max_age_hours=0,
    )
    print(f"index ids={len(index.get('all_ids') or [])}", flush=True)

    row = {
        "ho_ten": data.get("ho_ten") or args.name,
        "cccd": cccd,
        "nam_sinh": data.get("nam_sinh") or "",
        "ngay_sinh": data.get("ngay_sinh") or "",
        "gioi_tinh": data.get("gioi_tinh") or "",
    }
    resolved = resolve_tthc_matches(row, index, accounts=accounts)
    if resolved.status != "READY_IMPORT" or not resolved.matches:
        print(
            f"FAIL: match status={resolved.status} mode={getattr(resolved, 'mode', None)}",
            flush=True,
        )
        return 3

    print(
        f"MATCH mode={resolved.mode} name_mismatch={resolved.name_mismatch} "
        f"n={len(resolved.matches)}",
        flush=True,
    )

    tokens: dict[str, str] = {}
    for acct in accounts:
        tokens[acct["id"]] = authenticate(acct["user"], acct["password"])

    any_ok = False
    last_detail = ""
    results = []
    for mrec in resolved.matches:
        aid = str(mrec.get("_medinet_account") or accounts[0]["id"])
        pid = str(mrec.get("phieukhamId") or mrec.get("Id") or "")
        cdid = mrec.get("cdId")
        if not pid:
            continue
        acct = next((a for a in accounts if a["id"] == aid), accounts[0])

        def reauth(a=acct):
            tokens[a["id"]] = authenticate(a["user"], a["password"])
            return tokens[a["id"]]

        print(
            f"FILL [{aid}] pid={pid} HoTen={mrec.get('HoTen')!r} CCCD={mrec.get('CCCD')!r}",
            flush=True,
        )
        existing, tokens[aid] = load_cls_view(tokens[aid], pid, reauth=reauth)
        before_miss = cls_missing_lab_fields(
            existing,
            labs_to_form_payload(labs, phieukham_id=pid, gioi_tinh=data.get("gioi_tinh") or ""),
        )
        print(
            f"  before mchc={existing.get('XNM_MCHC')!r} rdw={existing.get('XNM_RDW')!r} "
            f"missing_vs_pdf={before_miss[:12]}",
            flush=True,
        )

        payload = labs_to_form_payload(
            labs, phieukham_id=pid, gioi_tinh=data.get("gioi_tinh") or ""
        )
        payload["LoaiKham"] = 5152
        if cdid not in (None, ""):
            try:
                payload["cdId"] = int(cdid)
            except Exception:
                pass

        print(
            f"  payload XNM_MCHC={payload.get('XNM_MCHC')!r} "
            f"XNM_RDW={payload.get('XNM_RDW')!r} "
            f"DuongMau={payload.get('SinhHoaMau_DuongMau')!r} "
            f"LucDoi={payload.get('SinhHoaMau_DuongMauLucDoi')!r} "
            f"fields={len(payload)}",
            flush=True,
        )

        ok, msg, _raw, tokens[aid] = insert_cls(tokens[aid], payload, reauth=reauth)
        verified, vdetail, tokens[aid] = verify_cls_saved(
            tokens[aid], pid, payload=payload, reauth=reauth
        )
        after, tokens[aid] = load_cls_view(tokens[aid], pid, reauth=reauth)
        still = cls_missing_lab_fields(after, payload)
        still_wo = [k for k in still if k != "SinhHoaMau_Ure" or "SinhHoaMau_Ure" in payload]
        print(
            f"  save ok={ok} msg={msg!r} verify={verified} detail={vdetail} "
            f"after_mchc={after.get('XNM_MCHC')!r} after_rdw={after.get('XNM_RDW')!r} "
            f"still={still_wo[:12]}",
            flush=True,
        )
        results.append(
            {
                "account": aid,
                "pid": pid,
                "ok": ok,
                "verified": verified,
                "msg": msg,
                "vdetail": vdetail,
                "still": still_wo,
                "payload_mchc": payload.get("XNM_MCHC"),
                "payload_rdw": payload.get("XNM_RDW"),
                "after_mchc": after.get("XNM_MCHC") if after else None,
                "after_rdw": after.get("XNM_RDW") if after else None,
            }
        )
        last_detail = vdetail
        if ok and verified and not still_wo:
            any_ok = True

    out = build / f"refill_{cccd}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(
        json.dumps(
            {
                "cccd": cccd,
                "pdf": str(pdf),
                "parse": {
                    "mchc": _lab_web(labs, "MCHC"),
                    "rdw": _lab_web(labs, "RDW"),
                    "glucose": _lab_web(labs, "Glucose"),
                    "glucose_fasting": _lab_web(labs, "Glucose_fasting"),
                    "urea": _lab_web(labs, "Urea"),
                },
                "name_mismatch": resolved.name_mismatch,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {out}", flush=True)
    if any_ok:
        print("OK refill + verify", flush=True)
        return 0
    print(f"FAIL/PARTIAL refill last={last_detail}", flush=True)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
