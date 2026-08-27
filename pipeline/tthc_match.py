"""TTHC matching: exact full name + year/phone/CCCD + dual-account picks.

Single code path for INBOX / MISSING / TK1 / TK2 rematch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from phase_b_preview import (
    _date_proximity_score,
    _fold_name,
    _index_recs,
    _parse_any_date,
    _year_from_ngaysinh,
    resolve_name_year,
)

ACCOUNT_TK1 = "pkdkthuankieu"
ACCOUNT_TK2 = "pkdk_Thuankieu"


@dataclass
class TTHCMatchResult:
    status: str  # READY_IMPORT | WAITING_ADMIN | AMBIGUOUS_NAME
    matches: list[dict] = field(default_factory=list)
    mode: str = ""


def normalize_phone_digits(raw: str) -> str:
    s = re.sub(r"\D", "", str(raw or ""))
    if not s or s in {".", "0"}:
        return ""
    return s


def rec_phone_digits(rec: dict) -> str:
    return normalize_phone_digits(str(rec.get("SDT") or rec.get("DienThoai") or ""))


def rec_cccd_digits(rec: dict) -> str:
    for key in ("CCCD", "SoCMND", "CMND", "SoCMT", "SoCCCD"):
        v = re.sub(r"\D", "", str(rec.get(key) or ""))
        if len(v) >= 9:
            return v
    return ""


def pdf_cccd_digits(row: dict) -> str:
    c = re.sub(r"\D", "", str(row.get("cccd") or ""))
    if len(c) >= 9:
        return c
    for key in ("chan_doan", "chandoan", "notes"):
        m = re.search(r"CCCD:\s*(\d{9,12})", str(row.get(key) or ""), re.I)
        if m:
            return m.group(1)
    return ""


def pdf_has_reference_params(row: dict) -> bool:
    return bool(
        str(row.get("nam_sinh") or "").strip()
        or str(row.get("ngay_sinh") or "").strip()
        or normalize_phone_digits(str(row.get("sdt") or ""))
        or pdf_cccd_digits(row)
    )


def pdf_result_date(row: dict) -> Any:
    d = _parse_any_date(row.get("ngay_co_kq"))
    if d:
        return d
    fname = str(row.get("file_name") or row.get("source_file") or "")
    stem = Path(fname).stem if fname else ""
    if re.match(r"^\d{6}-", stem):
        return _parse_any_date(stem[:6])
    return None


def collect_exact_name_candidates(index: dict, fold_name: str) -> list[dict]:
    if not fold_name:
        return []
    seen: set[Any] = set()
    out: list[dict] = []
    for bucket_key in ("by_fold_year", "by_name_year"):
        bucket = index.get(bucket_key) or {}
        for key in bucket:
            name_part = _fold_name((key.split("|", 1) + [""])[0])
            if name_part != fold_name:
                continue
            for rec in _index_recs(bucket, key):
                if not isinstance(rec, dict):
                    continue
                if _fold_name(str(rec.get("HoTen") or "")) != fold_name:
                    continue
                pid = rec.get("phieukhamId") or rec.get("Id")
                if pid in seen:
                    continue
                seen.add(pid)
                out.append(rec)
    return out


def score_tthc_candidate(rec: dict, row: dict) -> int:
    score = 0
    pdf_year = str(row.get("nam_sinh") or "").strip()
    rec_y = _year_from_ngaysinh(rec.get("NgaySinh"))
    if pdf_year and rec_y == pdf_year:
        score += 6
    pdf_dob = str(row.get("ngay_sinh") or "").strip()
    if pdf_dob:
        rd = _parse_any_date(rec.get("NgaySinh"))
        pd = _parse_any_date(pdf_dob)
        if rd and pd and rd == pd:
            score += 8
    ph = normalize_phone_digits(str(row.get("sdt") or ""))
    if ph and rec_phone_digits(rec) == ph:
        score += 10
    cc = pdf_cccd_digits(row)
    if cc and rec_cccd_digits(rec) == cc:
        score += 12
    score += _date_proximity_score(
        pdf_result_date(row),
        _parse_any_date(rec.get("NgayKham") or rec.get("KSKDK_NgayKham") or rec.get("NgayTao")),
    )
    return score


def _params_compatible(rec: dict, row: dict) -> bool:
    pdf_year = str(row.get("nam_sinh") or "").strip()
    rec_y = _year_from_ngaysinh(rec.get("NgaySinh"))
    ph = normalize_phone_digits(str(row.get("sdt") or ""))
    cc = pdf_cccd_digits(row)
    pdf_dob = str(row.get("ngay_sinh") or "").strip()

    if ph and rec_phone_digits(rec) and rec_phone_digits(rec) != ph:
        return False
    if cc and rec_cccd_digits(rec) and rec_cccd_digits(rec) != cc:
        return False
    if pdf_dob:
        rd = _parse_any_date(rec.get("NgaySinh"))
        pd = _parse_any_date(pdf_dob)
        if rd and pd and rd != pd:
            return False
    if pdf_year and rec_y and rec_y != pdf_year:
        if ph and rec_phone_digits(rec) == ph:
            return True
        if cc and rec_cccd_digits(rec) == cc:
            return True
        return False
    return True


def _params_conflict_reasons(rec: dict, row: dict) -> list[str]:
    """Human-readable why _params_compatible failed (for logs)."""
    reasons: list[str] = []
    pdf_year = str(row.get("nam_sinh") or "").strip()
    rec_y = _year_from_ngaysinh(rec.get("NgaySinh"))
    ph = normalize_phone_digits(str(row.get("sdt") or ""))
    rph = rec_phone_digits(rec)
    cc = pdf_cccd_digits(row)
    rcc = rec_cccd_digits(rec)
    pdf_dob = str(row.get("ngay_sinh") or "").strip()
    if ph and rph and rph != ph:
        reasons.append(f"phone pdf={ph} tthc={rph}")
    if cc and rcc and rcc != cc:
        reasons.append(f"cccd pdf={cc} tthc={rcc}")
    if pdf_dob:
        rd = _parse_any_date(rec.get("NgaySinh"))
        pd = _parse_any_date(pdf_dob)
        if rd and pd and rd != pd:
            reasons.append(f"dob pdf={pd.isoformat()} tthc={rd.isoformat()}")
    if pdf_year and rec_y and rec_y != pdf_year:
        reasons.append(f"year pdf={pdf_year} tthc={rec_y}")
    return reasons or ["unknown"]


def _unique_person_groups(recs: list[dict]) -> list[list[dict]]:
    """Group dual-account copies of the same person (CCCD / DOB / year)."""
    groups: list[list[dict]] = []
    for rec in recs:
        cc = rec_cccd_digits(rec)
        dob = _parse_any_date(rec.get("NgaySinh"))
        y = _year_from_ngaysinh(rec.get("NgaySinh"))
        placed = False
        for g in groups:
            g0 = g[0]
            g_cc = rec_cccd_digits(g0)
            g_dob = _parse_any_date(g0.get("NgaySinh"))
            g_y = _year_from_ngaysinh(g0.get("NgaySinh"))
            same = False
            if cc and g_cc and cc == g_cc:
                same = True
            elif dob and g_dob and dob == g_dob:
                same = True
            elif y and g_y and y == g_y and not cc and not g_cc:
                same = True
            if same:
                g.append(rec)
                placed = True
                break
        if not placed:
            groups.append([rec])
    return groups


def resolve_tthc_matches(
    row: dict,
    index: dict,
    accounts: list[dict] | None = None,
) -> TTHCMatchResult:
    """Exact folded full name; disambiguate with year / phone / CCCD / DOB."""
    name, year = resolve_name_year(row)
    fold = _fold_name(name)
    if not fold:
        return TTHCMatchResult("WAITING_ADMIN", [], "no_name")

    work = dict(row)
    if year:
        work["nam_sinh"] = year

    candidates = collect_exact_name_candidates(index, fold)
    if not candidates:
        return TTHCMatchResult("WAITING_ADMIN", [], "no_name_in_index")

    has_refs = pdf_has_reference_params(work)
    mode = ""

    if not has_refs:
        if len(candidates) == 1:
            pool = candidates
            mode = "unique_name_no_params"
        else:
            # Dual-account same person OK
            groups = _unique_person_groups(candidates)
            if len(groups) == 1:
                pool = groups[0]
                mode = "unique_person_no_params"
            else:
                return TTHCMatchResult("AMBIGUOUS_NAME", [], f"dup_name_{len(candidates)}")
    else:
        pool = [c for c in candidates if _params_compatible(c, work)]
        if not pool:
            # Soft fallback: exact name + birth year unique person.
            # PDF phone/CCCD/DOB typos must not block CLS fill onto the right TTHC
            # (e.g. TRƯƠNG QUANG CHƯƠNG 1999 — CCCD/phone on PDF ≠ form but year matches).
            pdf_year = str(work.get("nam_sinh") or "").strip()
            year_pool = [
                c
                for c in candidates
                if pdf_year and _year_from_ngaysinh(c.get("NgaySinh")) == pdf_year
            ]
            groups = _unique_person_groups(year_pool) if year_pool else []
            if len(groups) == 1:
                pool = groups[0]
                mode = "year_unique_soft"
            else:
                why = _params_conflict_reasons(candidates[0], work)
                return TTHCMatchResult(
                    "WAITING_ADMIN",
                    [],
                    f"params_conflict:{';'.join(why)}",
                )
        if len(pool) == 1:
            mode = mode or "params_unique"
        else:
            scored = sorted(pool, key=lambda r: score_tthc_candidate(r, work), reverse=True)
            top = score_tthc_candidate(scored[0], work)
            tied = [r for r in scored if score_tthc_candidate(r, work) == top]
            if len(tied) > 1:
                strong = [
                    r
                    for r in tied
                    if (
                        pdf_cccd_digits(work)
                        and rec_cccd_digits(r) == pdf_cccd_digits(work)
                    )
                    or (
                        normalize_phone_digits(str(work.get("sdt") or ""))
                        and rec_phone_digits(r)
                        == normalize_phone_digits(str(work.get("sdt") or ""))
                    )
                ]
                if len(strong) == 1:
                    pool = strong
                    mode = "params_strong_id"
                else:
                    # Same name+score on 2 accounts → keep both for dual-write.
                    # Ambiguous only if one account has 2+ people tied (no phone/CCCD).
                    by_a: dict[str, list] = {}
                    for r in tied:
                        aid = str(r.get("_medinet_account") or "")
                        by_a.setdefault(aid, []).append(r)
                    if any(len(v) > 1 for v in by_a.values()) and not (
                        pdf_cccd_digits(work)
                        or normalize_phone_digits(str(work.get("sdt") or ""))
                    ):
                        return TTHCMatchResult(
                            "AMBIGUOUS_NAME", [], f"tied_{len(tied)}"
                        )
                    pool = tied
                    mode = mode or "params_tied_multi_acct"
            else:
                pool = [scored[0]]
                mode = mode or "params_top_score"

    allowed = {a["id"] for a in accounts} if accounts else None
    by_acct: dict[str, tuple[int, dict]] = {}
    for rec in pool:
        aid = str(rec.get("_medinet_account") or "")
        if allowed is not None and aid and aid not in allowed:
            continue
        sc = score_tthc_candidate(rec, work)
        if aid not in by_acct or sc > by_acct[aid][0]:
            by_acct[aid] = (sc, rec)

    matches = [rec for _, rec in by_acct.values()]
    if not matches:
        return TTHCMatchResult("WAITING_ADMIN", [], "no_account_match")

    return TTHCMatchResult("READY_IMPORT", matches, mode)


def account_folder_name(account_id: str) -> str:
    if account_id == ACCOUNT_TK1:
        return "TK1"
    if account_id == ACCOUNT_TK2:
        return "TK2"
    return "TK1"


def accounts_label(matches: list[dict]) -> str:
    ids = sorted({str(r.get("_medinet_account") or "") for r in matches if r})
    return "+".join(x for x in ids if x)
