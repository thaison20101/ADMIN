"""Match TTHC (same rule as import) + check CLS on each TK — never insert."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

PIPE = Path(__file__).resolve().parents[1]
if str(PIPE) not in sys.path:
    sys.path.insert(0, str(PIPE))

from medinet_api import authenticate, cls_has_lab_values, load_cls_view  # noqa: E402
from pdf_extract import extract_pdf  # noqa: E402
from phase_b_preview import resolve_name_year  # noqa: E402
from tthc_match import (  # noqa: E402
    ACCOUNT_TK1,
    ACCOUNT_TK2,
    account_folder_name,
    resolve_tthc_matches,
)


def _patient_under18(nam_sinh: str, file_name: str = "") -> bool:
    try:
        from move_under18 import is_under18

        return is_under18(nam_sinh=nam_sinh or "", file_name=file_name or "")
    except Exception:
        return False


def _norm_aid(aid: str) -> str:
    a = (aid or "").strip()
    if a == ACCOUNT_TK1 or a == "pkdkthuankieu":
        return ACCOUNT_TK1
    if a == ACCOUNT_TK2 or a == "pkdk_Thuankieu":
        return ACCOUNT_TK2
    return a


def suggest_folder(
    *,
    match_status: str,
    tthc_scope: str,
    coverage: str,
    sample_kind: str,
    nam_sinh: str,
    file_name: str,
    primary_account: str,
) -> str:
    """Suggested archive folder by import routing rule (advisory only)."""
    if match_status == "AMBIGUOUS":
        return "UNDER 18"
    if match_status != "READY" or tthc_scope in {"", "NONE"}:
        return "MISSING"
    if sample_kind == "OTHER" or coverage not in {"FULL"}:
        return "ERROR"
    if tthc_scope == "BOTH":
        return "UNDER 18" if _patient_under18(nam_sinh, file_name) else "PROCESSED"
    if tthc_scope == "TK2":
        return "TK2"
    if tthc_scope == "TK1":
        return "TK1"
    return account_folder_name(primary_account or ACCOUNT_TK1)


def _cls_summary(
    *,
    match_status: str,
    tthc_scope: str,
    cls_tk1: str,
    cls_tk2: str,
) -> str:
    if match_status == "AMBIGUOUS":
        return "AMBIGUOUS"
    if match_status == "PARSE_FAIL":
        return "PARSE_FAIL"
    if match_status != "READY" or tthc_scope in {"", "NONE"}:
        return "NO_TTHC"
    vals: list[str] = []
    if tthc_scope in {"TK1", "BOTH"}:
        vals.append(cls_tk1)
    if tthc_scope in {"TK2", "BOTH"}:
        vals.append(cls_tk2)
    if not vals or all(v in {"SKIP", "N/A", ""} for v in vals):
        return "CLS_SKIPPED"
    yes = sum(1 for v in vals if v == "YES")
    no = sum(1 for v in vals if v == "NO")
    if yes >= 2:
        return "HAS_CLS_BOTH"
    if yes == 1 and no >= 1:
        return "PARTIAL_CLS"
    if yes == 1:
        return "HAS_CLS_ONE"
    if no == len(vals):
        return "NEED_CLS"
    return "NEED_CLS"


def check_one_pdf(
    pdf: Path,
    *,
    folder: str,
    index: dict,
    accounts: list[dict],
    tokens: dict[str, str],
    skip_cls: bool = False,
    sleep_s: float = 0.05,
) -> dict[str, Any]:
    """Parse + match + optional CLS check. Never calls insert_cls."""
    row: dict[str, Any] = {
        "folder": folder,
        "file_name": pdf.name,
        "path": str(pdf),
        "ho_ten": "",
        "nam_sinh": "",
        "ngay_sinh": "",
        "sdt": "",
        "cccd": "",
        "pdf_coverage": "",
        "sample_kind": "",
        "parse_ok": "NO",
        "match_status": "PARSE_FAIL",
        "match_mode": "",
        "tthc_tk1": "NO",
        "tthc_tk2": "NO",
        "tthc_scope": "NONE",
        "pid_tk1": "",
        "pid_tk2": "",
        "maphieu_tk1": "",
        "maphieu_tk2": "",
        "cls_tk1": "N/A",
        "cls_tk2": "N/A",
        "cls_summary": "NO_TTHC",
        "folder_nen": "MISSING",
        "primary_account": "",
    }

    try:
        data = extract_pdf(pdf)
    except Exception as e:
        row["match_mode"] = f"parse_exc:{e}"[:80]
        row["cls_summary"] = "PARSE_FAIL"
        row["folder_nen"] = "UNDER 18"
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

    row["ho_ten"] = str(data.get("ho_ten") or "")
    row["nam_sinh"] = str(data.get("nam_sinh") or "")
    row["ngay_sinh"] = str(data.get("ngay_sinh") or "")
    row["sdt"] = str(data.get("sdt") or "")
    row["cccd"] = str(data.get("cccd") or "")
    row["pdf_coverage"] = str(data.get("pdf_coverage") or "")
    row["sample_kind"] = str(data.get("sample_kind") or "BLOOD_URINE")
    row["parse_ok"] = "YES" if data.get("parse_ok") else "NO"

    if not data.get("parse_ok"):
        row["match_status"] = "PARSE_FAIL"
        row["folder_nen"] = "UNDER 18"
        row["cls_summary"] = "PARSE_FAIL"
        return row

    tthc = resolve_tthc_matches(data, index, accounts=accounts)
    row["match_mode"] = tthc.mode

    if tthc.status == "AMBIGUOUS_NAME":
        row["match_status"] = "AMBIGUOUS"
        row["cls_summary"] = "AMBIGUOUS"
        row["folder_nen"] = "UNDER 18"
        return row

    if tthc.status != "READY_IMPORT" or not tthc.matches:
        row["match_status"] = "NO_TTHC"
        row["cls_summary"] = "NO_TTHC"
        row["folder_nen"] = "MISSING"
        return row

    row["match_status"] = "READY"
    by_aid: dict[str, dict] = {}
    for rec in tthc.matches:
        aid = _norm_aid(str(rec.get("_medinet_account") or ""))
        if aid:
            by_aid[aid] = rec

    if ACCOUNT_TK1 in by_aid:
        row["tthc_tk1"] = "YES"
        rec = by_aid[ACCOUNT_TK1]
        row["pid_tk1"] = str(rec.get("phieukhamId") or rec.get("Id") or "")
        row["maphieu_tk1"] = str(rec.get("MaPhieu") or "")
    if ACCOUNT_TK2 in by_aid:
        row["tthc_tk2"] = "YES"
        rec = by_aid[ACCOUNT_TK2]
        row["pid_tk2"] = str(rec.get("phieukhamId") or rec.get("Id") or "")
        row["maphieu_tk2"] = str(rec.get("MaPhieu") or "")

    if row["tthc_tk1"] == "YES" and row["tthc_tk2"] == "YES":
        row["tthc_scope"] = "BOTH"
        row["primary_account"] = ACCOUNT_TK1
    elif row["tthc_tk2"] == "YES":
        row["tthc_scope"] = "TK2"
        row["primary_account"] = ACCOUNT_TK2
    elif row["tthc_tk1"] == "YES":
        row["tthc_scope"] = "TK1"
        row["primary_account"] = ACCOUNT_TK1
    else:
        # Unexpected account id — keep first match visible under TK1 columns
        aid0 = next(iter(by_aid), "")
        rec0 = by_aid.get(aid0) or {}
        row["tthc_scope"] = aid0 or "NONE"
        row["primary_account"] = aid0
        row["tthc_tk1"] = "YES" if aid0 else "NO"
        row["pid_tk1"] = str(rec0.get("phieukhamId") or rec0.get("Id") or "")
        row["maphieu_tk1"] = str(rec0.get("MaPhieu") or "")

    if skip_cls:
        row["cls_tk1"] = "SKIP" if row["tthc_tk1"] == "YES" else "N/A"
        row["cls_tk2"] = "SKIP" if row["tthc_tk2"] == "YES" else "N/A"
    else:
        for aid, key_cls, key_pid, key_tthc in (
            (ACCOUNT_TK1, "cls_tk1", "pid_tk1", "tthc_tk1"),
            (ACCOUNT_TK2, "cls_tk2", "pid_tk2", "tthc_tk2"),
        ):
            if row[key_tthc] != "YES":
                row[key_cls] = "N/A"
                continue
            pid = row.get(key_pid) or ""
            if not pid:
                row[key_cls] = "NO"
                continue
            tok = tokens.get(aid) or ""
            if not tok:
                row[key_cls] = "ERR"
                continue

            def _reauth(a: str = aid) -> str:
                for acct in accounts:
                    if acct["id"] == a:
                        tokens[a] = authenticate(acct["user"], acct["password"])
                        return tokens[a]
                return tokens.get(a) or ""

            try:
                existing, tokens[aid] = load_cls_view(tok, pid, reauth=_reauth)
                row[key_cls] = "YES" if cls_has_lab_values(existing) else "NO"
            except Exception as e:
                row[key_cls] = f"ERR:{e}"[:40]
            if sleep_s:
                time.sleep(sleep_s)

    row["cls_summary"] = _cls_summary(
        match_status=row["match_status"],
        tthc_scope=row["tthc_scope"],
        cls_tk1=str(row["cls_tk1"]),
        cls_tk2=str(row["cls_tk2"]),
    )
    row["folder_nen"] = suggest_folder(
        match_status=row["match_status"],
        tthc_scope=row["tthc_scope"],
        coverage=row["pdf_coverage"],
        sample_kind=row["sample_kind"],
        nam_sinh=row["nam_sinh"],
        file_name=pdf.name,
        primary_account=row["primary_account"],
    )
    return row
