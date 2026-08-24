"""Write multi-sheet PDF_CHECK Excel report."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

ALL_COLS = [
    "folder",
    "file_name",
    "path",
    "ho_ten",
    "nam_sinh",
    "ngay_sinh",
    "sdt",
    "cccd",
    "pdf_coverage",
    "sample_kind",
    "parse_ok",
    "match_status",
    "match_mode",
    "tthc_tk1",
    "tthc_tk2",
    "tthc_scope",
    "pid_tk1",
    "pid_tk2",
    "maphieu_tk1",
    "maphieu_tk2",
    "cls_tk1",
    "cls_tk2",
    "cls_summary",
    "folder_nen",
    "is_dup_name",
    "dup_folders",
    "dup_count",
    "same_hash_dup",
    "hash_dup_folders",
    "file_hash",
]


def _write_sheet(ws, rows: list[dict[str, Any]], cols: list[str] | None = None) -> None:
    cols = cols or ALL_COLS
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r.get(c, "") for c in cols])


def write_pdf_check_excel(rows: list[dict[str, Any]], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()

    ws_all = wb.active
    ws_all.title = "All"
    _write_sheet(ws_all, rows)

    dup = [r for r in rows if str(r.get("is_dup_name") or "") == "YES"]
    ws_dup = wb.create_sheet("Dup")
    _write_sheet(ws_dup, dup)

    need = [
        r
        for r in rows
        if str(r.get("cls_summary") or "") in {"NEED_CLS", "PARTIAL_CLS"}
    ]
    ws_need = wb.create_sheet("NeedCLS")
    _write_sheet(ws_need, need)

    has = [
        r
        for r in rows
        if str(r.get("cls_summary") or "") in {"HAS_CLS_ONE", "HAS_CLS_BOTH"}
    ]
    ws_has = wb.create_sheet("HasCLS")
    _write_sheet(ws_has, has)

    no_tthc = [
        r
        for r in rows
        if str(r.get("cls_summary") or "") in {"NO_TTHC", "PARSE_FAIL"}
        or str(r.get("match_status") or "") in {"NO_TTHC", "PARSE_FAIL"}
    ]
    ws_miss = wb.create_sheet("NoTTHC")
    _write_sheet(ws_miss, no_tthc)

    amb = [r for r in rows if str(r.get("match_status") or "") == "AMBIGUOUS"]
    ws_amb = wb.create_sheet("Ambiguous")
    _write_sheet(ws_amb, amb)

    # folder mismatch: current folder != suggested
    mismatch = [
        r
        for r in rows
        if r.get("folder_nen")
        and r.get("folder")
        and str(r.get("folder")) != str(r.get("folder_nen"))
        and str(r.get("match_status") or "") == "READY"
    ]
    ws_mm = wb.create_sheet("FolderMismatch")
    _write_sheet(ws_mm, mismatch)

    ws_sum = wb.create_sheet("Summary")
    ws_sum.append(["metric", "value"])
    ws_sum["A1"].font = Font(bold=True)
    ws_sum["B1"].font = Font(bold=True)
    ws_sum.append(["total_pdf", len(rows)])
    ws_sum.append(["dup_name", len(dup)])
    ws_sum.append(["need_cls", len(need)])
    ws_sum.append(["has_cls", len(has)])
    ws_sum.append(["no_tthc", len(no_tthc)])
    ws_sum.append(["ambiguous", len(amb)])
    ws_sum.append(["folder_mismatch", len(mismatch)])
    ws_sum.append([])
    ws_sum.append(["cls_summary", "count"])
    for k, v in Counter(str(r.get("cls_summary") or "") for r in rows).most_common():
        ws_sum.append([k, v])
    ws_sum.append([])
    ws_sum.append(["tthc_scope", "count"])
    for k, v in Counter(str(r.get("tthc_scope") or "") for r in rows).most_common():
        ws_sum.append([k, v])
    ws_sum.append([])
    ws_sum.append(["folder", "count"])
    for k, v in Counter(str(r.get("folder") or "") for r in rows).most_common():
        ws_sum.append([k, v])

    wb.save(out_path)
    return out_path
