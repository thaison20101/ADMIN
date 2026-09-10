#!/usr/bin/env python3
"""Force re-fill one patient CLS from PDF (bypass gap-only skip).

Default: VONG QUOC CHU / 079087013411 — form still missing MCHC/RDW.

PDF lab files often have NO CCCD in text (only in Medinet TTHC). Finder
must match by filename / ho_ten / nam_sinh, not require CCCD inside PDF.

Usage (may A):
  cd C:\\Users\\thais\\ADMIN
  python .\\pipeline\\refill_one_patient.py
  python .\\pipeline\\refill_one_patient.py --pdf \"G:\\Drive của tôi\\PKDK_Thuankieu_Pipeline\\TK2\\300826-497079 - VONG QUOC CHU - 1987 - M.pdf\"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
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


def fold_ascii(s: str) -> str:
    """VÒNG QUỐC CHỦ → VONG QUOC CHU (for path/name compare)."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip().upper()


def name_tokens(name: str) -> list[str]:
    return [t for t in fold_ascii(name).split() if len(t) >= 2]


def path_matches_name(path: Path, name: str) -> bool:
    folded = fold_ascii(str(path))
    toks = name_tokens(name)
    if len(toks) < 2:
        return fold_ascii(name) in folded if name else False
    # Require all tokens present (order-independent) — handles VONG QUOC CHU
    return all(t in folded for t in toks)


def _iter_pdfs_shallow_then_deep(folder: Path):
    """Prefer direct children (fast on Drive), then rglob."""
    if not folder.exists():
        print(f"  WARN folder missing: {folder}", flush=True)
        return
    try:
        for p in folder.glob("*.pdf"):
            yield p
        for p in folder.glob("*.PDF"):
            if p.suffix == ".PDF":
                yield p
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN glob {folder}: {exc}", flush=True)
    try:
        for p in folder.rglob("*.pdf"):
            yield p
        for p in folder.rglob("*.PDF"):
            yield p
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN rglob {folder}: {exc}", flush=True)


def _score_candidate(pdf: Path, data: dict, cccd: str, name: str) -> int:
    """Higher = better. Negative = reject."""
    pdf_cccd = re.sub(r"\D", "", str(data.get("cccd") or ""))
    target = re.sub(r"\D", "", cccd or "")
    ho = fold_ascii(str(data.get("ho_ten") or ""))
    want = fold_ascii(name)
    year = str(data.get("nam_sinh") or "")
    # Year from filename e.g. ... - 1987 - M.pdf
    m_y = re.search(r"\b(19|20)\d{2}\b", pdf.name)
    fname_year = m_y.group(0) if m_y else ""

    if pdf_cccd and target and pdf_cccd != target:
        return -1  # hard reject wrong person
    score = 0
    if pdf_cccd and pdf_cccd == target:
        score += 100
    if path_matches_name(pdf, name):
        score += 40
    if ho and want and (ho == want or want in ho or ho in want):
        score += 50
    if year and year in {"1987"} and name and "QUOC CHU" in want:
        score += 10
    if fname_year == "1987" and path_matches_name(pdf, name):
        score += 15
    if score < 40:
        return -1  # need at least filename name match
    return score


def _find_pdf(cccd: str, name_hint: str, explicit: Path | None) -> Path | None:
    if explicit is not None:
        p = Path(explicit)
        if p.is_file():
            return p
        # Allow glob: parent folder + pattern in name
        if any(ch in str(explicit) for ch in "*?"):
            parent = p.parent if str(p.parent) not in {"", "."} else Path(".")
            try:
                hits = sorted(
                    (h for h in parent.glob(p.name) if h.is_file()),
                    key=lambda x: x.stat().st_mtime,
                    reverse=True,
                )
            except Exception as exc:  # noqa: BLE001
                hits = []
                print(f"WARN glob --pdf: {exc}", flush=True)
            if hits:
                print(f"  --pdf glob hit: {hits[0]}", flush=True)
                return hits[0]
        print(f"WARN --pdf not a file: {explicit}", flush=True)

    sync = discover_pipeline_root()
    build = discover_build_root()
    folders = ensure_standard_folders(sync, build)
    print(f"sync={sync}", flush=True)

    order = [
        "TK2",
        "TK1",
        "ERROR",
        "CCCD",
        "PROCESSED",
        "MISSING",
        "INBOX_CLS",
        "UNDER 18",
    ]

    # Pass 1: filename-only (no pdfplumber) — critical when Drive is slow/paused
    name_hits: list[Path] = []
    seen: set[str] = set()
    for folder_name in order:
        root = folders.get(folder_name) or (sync / folder_name)
        print(f"  scan {folder_name}: {root} exists={root.exists()}", flush=True)
        for pdf in _iter_pdfs_shallow_then_deep(root):
            key = str(pdf).lower()
            if key in seen:
                continue
            seen.add(key)
            if path_matches_name(pdf, name_hint) or (cccd and cccd in str(pdf)):
                name_hits.append(pdf)
                print(f"  name-hit: {pdf}", flush=True)

    if not name_hits:
        # Last resort: glob patterns under sync
        patterns = [
            f"*VONG*QUOC*CHU*.pdf",
            f"*Vong*Quoc*Chu*.pdf",
            f"*{cccd}*.pdf" if cccd else "",
        ]
        for folder_name in order:
            root = folders.get(folder_name) or (sync / folder_name)
            if not root.exists():
                continue
            for pat in patterns:
                if not pat:
                    continue
                try:
                    for pdf in root.glob(pat):
                        name_hits.append(pdf)
                        print(f"  glob-hit: {pdf}", flush=True)
                    for pdf in root.rglob(pat):
                        name_hits.append(pdf)
                except Exception as exc:  # noqa: BLE001
                    print(f"  WARN glob {pat}: {exc}", flush=True)

    if not name_hits:
        return None

    # Pass 2: score by extract when possible; accept best name hit even if CCCD absent
    best: Path | None = None
    best_score = -1
    for pdf in name_hits:
        try:
            data = extract_pdf(pdf)
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN extract fail {pdf.name}: {exc}", flush=True)
            # Still usable by filename alone
            sc = 40 if path_matches_name(pdf, name_hint) else -1
            data = {}
        else:
            sc = _score_candidate(pdf, data, cccd, name_hint)
            print(
                f"  cand {pdf.name}: score={sc} cccd={data.get('cccd')!r} "
                f"ho_ten={data.get('ho_ten')!r} "
                f"mchc={(data.get('labs') or {}).get('MCHC')}",
                flush=True,
            )
        if sc > best_score:
            best_score = sc
            best = pdf

    if best is None and name_hits:
        # Absolute fallback: newest filename match
        try:
            best = max(name_hits, key=lambda p: p.stat().st_mtime)
            print(f"  fallback newest name-hit: {best}", flush=True)
        except Exception:
            best = name_hits[0]
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
        print("FAIL: khong tim thay PDF tren G: cho CCCD/ten nay", flush=True)
        print(
            "HINT: Google Drive dang pause sync — bam 'Tiep tuc dong bo hoa'. "
            "Hoac chi dinh file: --pdf \"G:\\Drive của tôi\\PKDK_Thuankieu_Pipeline\\TK2\\300826-497079 - VONG QUOC CHU*.pdf\"",
            flush=True,
        )
        return 2
    print(f"PDF: {pdf}", flush=True)

    data = extract_pdf(pdf)
    # Force CCCD from CLI when PDF text lacks it (common for lab PDFs)
    if not (data.get("cccd") or "").strip():
        data["cccd"] = cccd
        print(f"NOTE: PDF khong co CCCD trong text — dung CLI cccd={cccd}", flush=True)
    if not (data.get("ho_ten") or "").strip():
        data["ho_ten"] = args.name

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
            "WARN: PDF parse chua ra MCHC/RDW — kiem tra text PDF (Ghi chu 303 / 11.4)",
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
        "nam_sinh": data.get("nam_sinh") or "1987",
        "ngay_sinh": data.get("ngay_sinh") or "",
        "gioi_tinh": data.get("gioi_tinh") or "",
        "file_name": pdf.name,
        "source_file": str(pdf),
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
