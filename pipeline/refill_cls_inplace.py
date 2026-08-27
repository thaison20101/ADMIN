#!/usr/bin/env python3
"""Điền lại CLS từ PDF tại chỗ — không move file.

Ưu tiên folder:
  P. BÌNH TÂY - TRƯỜNG THCS NGUYỄN ĐỨC CẢNH - NGÀY 13-08-2026 - 165 CASE

  python pipeline/refill_cls_inplace.py
  python pipeline/refill_cls_inplace.py --apply
  python pipeline/refill_cls_inplace.py --toan-bo --apply
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PIPE = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPE))

from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()

from drive_paths import g_pipeline_live, local_work_build, require_g_on_windows, resolve_g_sync  # noqa: E402
from medinet_api import (  # noqa: E402
    LAB_TO_FORM,
    authenticate,
    cls_has_lab_values,
    cls_missing_lab_fields,
    insert_cls,
    labs_to_form_payload,
    load_cls_view,
    verify_cls_saved,
)
from medinet_creds import MEDINET_ACCOUNTS  # noqa: E402
from pdf_extract import extract_pdf  # noqa: E402
from phase_b_preview import load_config, load_or_fetch_merged_unit_index, resolve_name_year  # noqa: E402
from single_instance import acquire_lock, release_lock  # noqa: E402
from tthc_match import ACCOUNT_TK1, ACCOUNT_TK2, resolve_tthc_matches  # noqa: E402

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font  # noqa: E402

DEFAULT_FOLDER_HINTS = (
    "BINH TAY",
    "NGUYEN DUC CANH",
    "13-08-2026",
    "165 CASE",
)

# Exact folder name under sync root — refill this first (no move).
FIRST_FOLDER_NAMES = ("first", "First", "FIRST")

TOAN_BO_FOLDERS = (
    "PROCESSED",
    "TK1",
    "TK2",
    "UNDER 18",
    "ERROR",
    "INBOX_CLS",
)

ACTION_COLS = [
    "Tên file",
    "Họ tên",
    "Năm sinh",
    "Folder nguồn",
    "Phạm vi TTHC",
    "Trường trên PDF",
    "Thiếu trước",
    "Đã điền",
    "Kết quả",
    "Ghi chú",
]


def _today_dmy() -> str:
    return date.today().strftime("%d/%m/%Y")


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).upper().strip()


def find_first_folder(sync: Path) -> Path | None:
    """Find sync/<first> (case-insensitive exact name). Prefer this for refill."""
    if not sync.exists():
        return None
    try:
        children = list(sync.iterdir())
    except OSError:
        return None
    wanted = {n.lower() for n in FIRST_FOLDER_NAMES}
    for p in children:
        try:
            if p.is_dir() and p.name.lower() in wanted:
                return p
        except OSError:
            continue
    return None


def find_priority_folder(sync: Path, hints: tuple[str, ...] = DEFAULT_FOLDER_HINTS) -> Path | None:
    """Prefer folder `first`, else Bình Tây 165-case under sync root."""
    first = find_first_folder(sync)
    if first is not None:
        return first
    if not sync.exists():
        return None
    best: Path | None = None
    best_score = 0
    try:
        children = list(sync.iterdir())
    except OSError:
        return None
    for p in children:
        try:
            if not p.is_dir():
                continue
        except OSError:
            continue
        name = _fold(p.name)
        score = sum(1 for h in hints if h in name)
        if score > best_score:
            best_score = score
            best = p
    if best is not None and best_score >= 2:
        return best
    return None


def list_pdfs_rglob(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    try:
        return sorted(folder.rglob("*.pdf"), key=lambda p: p.name.lower())
    except OSError:
        return []


def _norm_aid(aid: str) -> str:
    a = (aid or "").strip()
    if a in {ACCOUNT_TK1, "pkdkthuankieu"}:
        return ACCOUNT_TK1
    if a in {ACCOUNT_TK2, "pkdk_Thuankieu"}:
        return ACCOUNT_TK2
    return a


def _payload_lab_keys(payload: dict) -> list[str]:
    return sorted(k for k in payload if k in LAB_TO_FORM.values())


def refill_one(
    pdf: Path,
    *,
    folder_label: str,
    index: dict,
    accounts: list[dict],
    tokens: dict[str, str],
    apply: bool,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "Tên file": pdf.name,
        "Họ tên": "",
        "Năm sinh": "",
        "Folder nguồn": folder_label,
        "Phạm vi TTHC": "Không có",
        "Trường trên PDF": "",
        "Thiếu trước": "",
        "Đã điền": "",
        "Kết quả": "Dry-run" if not apply else "Thành công",
        "Ghi chú": "",
    }
    try:
        data = extract_pdf(pdf)
    except Exception as e:
        row["Kết quả"] = "Lỗi"
        row["Ghi chú"] = f"parse:{e}"[:120]
        return row

    data["file_name"] = pdf.name
    data["source_file"] = str(pdf)
    name, year = resolve_name_year(
        {
            "ho_ten": data.get("ho_ten") or "",
            "nam_sinh": data.get("nam_sinh") or "",
            "file_name": pdf.name,
            "source_file": str(pdf),
        }
    )
    if name:
        data["ho_ten"] = name
    if year:
        data["nam_sinh"] = year
    row["Họ tên"] = str(data.get("ho_ten") or "")
    row["Năm sinh"] = str(data.get("nam_sinh") or "")

    if not data.get("parse_ok"):
        row["Kết quả"] = "Lỗi"
        row["Ghi chú"] = "parse_ok=false"
        return row

    tthc = resolve_tthc_matches(data, index, accounts=accounts)
    if tthc.status == "AMBIGUOUS_NAME":
        row["Kết quả"] = "Bỏ qua"
        row["Ghi chú"] = f"ambiguous:{tthc.mode}"
        return row
    if tthc.status != "READY_IMPORT" or not tthc.matches:
        row["Kết quả"] = "Bỏ qua"
        row["Ghi chú"] = f"no_tthc:{tthc.mode}"
        return row

    by_aid: dict[str, dict] = {}
    for rec in tthc.matches:
        aid = _norm_aid(str(rec.get("_medinet_account") or ""))
        if aid:
            by_aid[aid] = rec
    if ACCOUNT_TK1 in by_aid and ACCOUNT_TK2 in by_aid:
        row["Phạm vi TTHC"] = "Cả 2 TK"
    elif ACCOUNT_TK2 in by_aid:
        row["Phạm vi TTHC"] = "TK2"
    elif ACCOUNT_TK1 in by_aid:
        row["Phạm vi TTHC"] = "TK1"

    def make_reauth(aid: str):
        def _r():
            for acct in accounts:
                if acct["id"] == aid:
                    tokens[aid] = authenticate(acct["user"], acct["password"])
                    return tokens[aid]
            return tokens.get(aid) or ""

        return _r

    all_pdf_fields: list[str] = []
    all_missing: list[str] = []
    all_filled: list[str] = []
    notes: list[str] = []

    for aid, mrec in by_aid.items():
        pid = str(mrec.get("phieukhamId") or mrec.get("Id") or "")
        cdid = mrec.get("cdId")
        if not pid:
            notes.append(f"{aid}:no_pid")
            continue
        payload = labs_to_form_payload(
            data.get("labs") or {},
            phieukham_id=pid,
            gioi_tinh=data.get("gioi_tinh") or "",
        )
        payload["LoaiKham"] = 5152
        if cdid not in (None, ""):
            payload["cdId"] = int(cdid)
        pdf_fields = _payload_lab_keys(payload)
        all_pdf_fields.extend(f"{aid}:{k}" for k in pdf_fields)

        # Always compare web vs FULL PDF payload (every field PDF has).
        pdf_has_urea = "Urea" in (data.get("labs") or {})

        def _miss_wo_optional_urea(existing_row: dict | None) -> list[str]:
            if not cls_has_lab_values(existing_row):
                miss0 = list(pdf_fields)
            else:
                miss0 = cls_missing_lab_fields(existing_row, payload)
            if not pdf_has_urea:
                miss0 = [k for k in miss0 if k != "SinhHoaMau_Ure"]
            return miss0

        if not apply:
            try:
                existing, tokens[aid] = load_cls_view(
                    tokens[aid], pid, reauth=make_reauth(aid)
                )
                miss = _miss_wo_optional_urea(existing)
                all_missing.extend(f"{aid}:{k}" for k in miss)
                all_filled.extend(f"{aid}:{k}" for k in miss)  # would fill
            except Exception as e:
                notes.append(f"{aid}:dry_load:{e}"[:40])
                all_missing.extend(f"{aid}:{k}" for k in pdf_fields)
            continue

        # APPLY: always insert full payload — never skip as "da_du".
        # Set (= Lưu): retry until Get+FormViewer shows ALL PDF fields (blood + urine).
        existing, tokens[aid] = load_cls_view(tokens[aid], pid, reauth=make_reauth(aid))
        miss = _miss_wo_optional_urea(existing)
        all_missing.extend(f"{aid}:{k}" for k in miss)

        still: list[str] = list(pdf_fields)
        ok, msg, verified, vdetail = False, "", False, ""
        max_set = 3
        for attempt in range(max_set):
            ok, msg, _raw, tokens[aid] = insert_cls(
                tokens[aid], payload, reauth=make_reauth(aid)
            )
            time.sleep(0.12 * (attempt + 1))
            verified, vdetail, tokens[aid] = verify_cls_saved(
                tokens[aid], pid, payload=payload, reauth=make_reauth(aid)
            )
            existing2, tokens[aid] = load_cls_view(
                tokens[aid], pid, reauth=make_reauth(aid)
            )
            still = _miss_wo_optional_urea(existing2)
            if not still:
                break
            # Partial persist — retry full Set (urine format branches inside insert_cls)
            notes.append(
                f"{aid}:retry_set={attempt + 1}/{max_set};con_thieu={still[:8]}"
            )

        filled = [k for k in pdf_fields if k not in still]
        if not pdf_has_urea:
            filled = [k for k in filled if k != "SinhHoaMau_Ure"]
        all_filled.extend(f"{aid}:{k}" for k in filled)
        notes.append(
            f"{aid}:ok={ok};ver={verified};miss_truoc={len(miss)};{vdetail}"[:120]
        )
        if still:
            row["Kết quả"] = "Một phần"
            notes.append(f"{aid}:con_thieu={still[:12]}")
        elif not verified:
            # Get+FormViewer empty / mismatch — never false Thành công
            row["Kết quả"] = "Một phần"
            notes.append(f"{aid}:verify_fail:{vdetail}"[:80])
        elif not ok:
            row["Kết quả"] = "Một phần"
            notes.append(f"{aid}:set_fail:{msg}"[:80])

    row["Trường trên PDF"] = ", ".join(sorted(set(all_pdf_fields)))[:500]
    row["Thiếu trước"] = ", ".join(sorted(set(all_missing)))[:500]
    row["Đã điền"] = ", ".join(sorted(set(all_filled)))[:500]
    row["Ghi chú"] = "; ".join(notes)[:300]
    if row["Kết quả"] not in {"Lỗi", "Bỏ qua", "Một phần"}:
        if not all_pdf_fields:
            row["Kết quả"] = "Bỏ qua"
            row["Ghi chú"] = (row["Ghi chú"] + ";khong_co_truong_pdf")[:300]
        elif apply:
            # Only Thành công when every account finished with no remaining miss
            row["Kết quả"] = "Thành công"
        else:
            row["Kết quả"] = "Dry-run"
    return row


def write_refill_excel(rows: list[dict], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Chi tiết hành động"
    ws.append(ACTION_COLS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r.get(c, "") for c in ACTION_COLS])

    ws_all = wb.create_sheet("Tất cả")
    ws_all.append(ACTION_COLS)
    for c in ws_all[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws_all.append([r.get(c, "") for c in ACTION_COLS])

    need = [r for r in rows if r.get("Thiếu trước")]
    ws_need = wb.create_sheet("Cần điền")
    ws_need.append(ACTION_COLS)
    for c in ws_need[1]:
        c.font = Font(bold=True)
    for r in need:
        ws_need.append([r.get(c, "") for c in ACTION_COLS])

    skip = [r for r in rows if r.get("Kết quả") == "Bỏ qua"]
    ws_skip = wb.create_sheet("Khong TTHC - Bo qua")
    ws_skip.append(ACTION_COLS)
    for c in ws_skip[1]:
        c.font = Font(bold=True)
    for r in skip:
        ws_skip.append([r.get(c, "") for c in ACTION_COLS])

    ws_sum = wb.create_sheet("Tóm tắt")
    ws_sum.append(["Chỉ số", "Giá trị"])
    ws_sum["A1"].font = Font(bold=True)
    ws_sum.append(["Tổng PDF", len(rows)])
    ws_sum.append(["Cần điền", len(need)])
    ws_sum.append(["Bỏ qua", len(skip)])
    ws_sum.append([])
    ws_sum.append(["Kết quả", "Số lượng"])
    for k, v in Counter(str(r.get("Kết quả") or "") for r in rows).most_common():
        ws_sum.append([k, v])
    wb.save(out_path)
    return out_path


def run_refill(
    *,
    apply: bool = False,
    toan_bo: bool = False,
    folder: str = "",
    limit: int = 0,
) -> dict:
    lock = acquire_lock("refill_cls_inplace")
    if lock is None:
        safe_print("ABORT: refill dang chay (lock).")
        return {"abort": "locked"}
    try:
        if sys.platform.startswith("win") and g_pipeline_live() is None:
            safe_print("ABORT: G: chua mount.")
            return {"abort": "g_missing"}
        cfg = load_config()
        sync = resolve_g_sync(cfg)
        if sys.platform.startswith("win") and not require_g_on_windows(sync):
            safe_print(f"ABORT: chi G: sync={sync}")
            return {"abort": "not_g"}

        targets: list[tuple[str, Path]] = []
        if folder.strip():
            p = Path(folder.strip())
            if not p.is_absolute():
                p = sync / folder.strip()
            targets.append((p.name, p))
        elif toan_bo:
            for name in TOAN_BO_FOLDERS:
                targets.append((name, sync / name))
        else:
            found = find_priority_folder(sync)
            if found is None:
                safe_print(
                    "ABORT: khong tim thay folder 'first' hoac Binh Tay / 165 CASE"
                )
                safe_print(f"SYNC={sync}")
                try:
                    for c in sorted(sync.iterdir()):
                        if c.is_dir():
                            safe_print(f"  - {c.name}")
                except OSError:
                    pass
                return {"abort": "folder_not_found"}
            targets.append((found.name, found))
            if found.name.lower() == "first":
                safe_print("Uu tien: folder first (khong move)")

        mode = "APPLY" if apply else "DRY-RUN"
        safe_print(f"========== DIEN LAI CLS ({mode}) ==========")
        safe_print(f"SYNC: {sync}")
        safe_print("Rule: FULL PDF fields -> web (trong/ngoai khoang), KHONG MOVE, KHONG Excel")

        pdfs: list[tuple[str, Path]] = []
        for label, d in targets:
            found_pdfs = list_pdfs_rglob(d)
            safe_print(f"  {label}: {len(found_pdfs)} pdf")
            for p in found_pdfs:
                pdfs.append((label, p))
        if limit > 0:
            pdfs = pdfs[:limit]
            safe_print(f"Limited: {len(pdfs)}")

        accounts = [dict(a) for a in MEDINET_ACCOUNTS[:2]]
        tokens: dict[str, str] = {}
        for acct in accounts:
            tokens[acct["id"]] = authenticate(acct["user"], acct["password"])

        date_from = (cfg.get("medinet") or {}).get("date_from") or "01/07/2026"
        date_to = ((cfg.get("medinet") or {}).get("date_to") or "").strip() or _today_dmy()
        cache_dir = ROOT / "pipeline" / "work" / "index_cache"
        index = load_or_fetch_merged_unit_index(
            accounts, date_from, date_to, cache_dir=cache_dir, max_age_hours=3.0
        )

        results: list[dict] = []
        t0 = time.time()
        for i, (label, pdf) in enumerate(pdfs, 1):
            r = refill_one(
                pdf,
                folder_label=label,
                index=index,
                accounts=accounts,
                tokens=tokens,
                apply=apply,
            )
            results.append(r)
            if i == 1 or i % 25 == 0 or i == len(pdfs):
                safe_print(
                    f"  [{i}/{len(pdfs)}] {r.get('Họ tên') or pdf.name} "
                    f"scope={r.get('Phạm vi TTHC')} ketqua={r.get('Kết quả')}"
                )

        # No Excel this run (hourly later). Short console + txt log only.
        build = local_work_build()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        tag = "TOANBO" if toan_bo else "FOLDER"
        out_log = build / "logs" / f"REFILL_{tag}_{stamp}.txt"
        counts = Counter(str(r.get("Kết quả") or "") for r in results)
        lines = [
            f"mode={mode}",
            f"toan_bo={toan_bo}",
            f"total={len(results)}",
            f"elapsed_s={time.time() - t0:.0f}",
            "excel=SKIP",
            "",
            "ket_qua:",
        ]
        for k, v in counts.most_common():
            lines.append(f"  {k}={v}")
        # Sample partial cases for console follow-up
        partials = [r for r in results if r.get("Kết quả") == "Một phần"][:20]
        if partials:
            lines.append("")
            lines.append("mau_mot_phan:")
            for r in partials:
                lines.append(
                    f"  {r.get('Họ tên')}|{r.get('Tên file')}|thieu={r.get('Thiếu trước')}"
                )
        out_log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        safe_print(f"Log: {out_log}")
        for k, v in counts.most_common():
            safe_print(f"  {k}={v}")
        safe_print(f"DONE ({mode}) - khong move PDF, khong Excel")
        return {"ok": True, "log": str(out_log), "total": len(results), "counts": dict(counts)}
    finally:
        release_lock(lock)


def main() -> int:
    ap = argparse.ArgumentParser(description="Dien lai CLS tu PDF — khong move")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--toan-bo", action="store_true", help="Quet PROCESSED/TK1/TK2/...")
    ap.add_argument("--folder", default="", help="Path hoac ten folder duoi sync")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    res = run_refill(
        apply=bool(args.apply),
        toan_bo=bool(args.toan_bo),
        folder=str(args.folder or ""),
        limit=int(args.limit or 0),
    )
    return 2 if res.get("abort") else 0


if __name__ == "__main__":
    raise SystemExit(main())
