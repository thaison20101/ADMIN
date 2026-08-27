#!/usr/bin/env python3
"""Audit PDF parse for known anomaly patterns (no Medinet, no move).

Priority order:
  1) sync/first (or --first / ./first)
  2) Batch_* under cwd
  3) PROCESSED / TK1 / TK2 / UNDER 18 / ERROR / INBOX_CLS

Flags:
  - sci9: WBC/PLT/count == 9 while text has 10^9  (legacy bug)
  - sci12: RBC == 12 while text has 10^12
  - missing_core: blood core missing though labels present
  - missing_urine: urine block present but few urine labs
  - bound_as_value: value equals a stripped ref bound
  - wild_range: RBC>8 or WBC>50 or PLT<20 with alternate number on line

  python pipeline/audit_pdf_parse.py
  python pipeline/audit_pdf_parse.py --limit 200
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPE = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPE))

from win_console import safe_print, setup_utf8_stdio  # noqa: E402

setup_utf8_stdio()

from drive_paths import resolve_g_sync  # noqa: E402
from pdf_extract import extract_pdf, read_pdf_text  # noqa: E402
from phase_b_preview import load_config  # noqa: E402

TOAN_BO = (
    "PROCESSED",
    "TK1",
    "TK2",
    "UNDER 18",
    "ERROR",
    "INBOX_CLS",
)

_CORE = ("WBC", "RBC", "HGB", "PLT", "MCV", "MCH", "MCHC")
_COUNTS = (
    "WBC",
    "PLT",
    "Neutrophils_count",
    "Lymphocytes_count",
    "Monocytes_count",
    "Eosinophils_count",
    "Basophils_count",
)


def _web_num(labs: dict, key: str) -> float | None:
    item = labs.get(key) or {}
    v = item.get("value_web")
    if v in (None, ""):
        v = item.get("value_raw")
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ".").lstrip("<>"))
    except Exception:
        return None


def find_first_dir(roots: list[Path]) -> Path | None:
    for root in roots:
        if not root or not root.exists():
            continue
        try:
            for p in root.iterdir():
                if p.is_dir() and p.name.lower() == "first":
                    return p
        except OSError:
            continue
        # also allow root itself named first
        if root.name.lower() == "first" and root.is_dir():
            return root
    return None


def collect_targets(sync: Path | None, *, cwd: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    roots = [sync, cwd, cwd / "PKDK_Thuankieu_Pipeline"]
    roots = [r for r in roots if r is not None]

    first = find_first_dir(roots)
    if first is not None:
        out.append(("first", first))

    for batch in sorted(cwd.glob("Batch_*")):
        if batch.is_dir():
            out.append((batch.name, batch))

    if sync and sync.exists():
        for name in TOAN_BO:
            d = sync / name
            if d.is_dir():
                out.append((name, d))
        # also Batch under sync
        for batch in sorted(sync.glob("Batch_*")):
            if batch.is_dir() and (batch.name, batch) not in out:
                out.append((batch.name, batch))
    return out


def audit_one(pdf: Path) -> list[str]:
    flags: list[str] = []
    try:
        text = read_pdf_text(pdf)
        data = extract_pdf(pdf)
    except Exception as e:
        return [f"parse_error:{e}"]
    labs = data.get("labs") or {}
    has_10e9 = bool(re.search(r"10\s*\^\s*9", text))
    has_10e12 = bool(re.search(r"10\s*\^\s*12", text))

    for k in _COUNTS:
        n = _web_num(labs, k)
        if n is not None and abs(n - 9.0) < 1e-9 and has_10e9:
            flags.append(f"sci9:{k}=9")
    rbc = _web_num(labs, "RBC")
    if rbc is not None and abs(rbc - 12.0) < 1e-9 and has_10e12:
        flags.append("sci12:RBC=12")

    for k in ("WBC", "RBC", "HGB", "PLT"):
        if re.search(rf"(?i)\b{k}\b|Leukocytes|Erythrocytes|Hemoglobin|Platelets", text):
            if _web_num(labs, k) is None and k not in {"HGB"}:
                # HGB often labeled Hb
                if k == "WBC" and not re.search(r"(?i)Leukocytes|WBC", text):
                    continue
                flags.append(f"missing_core:{k}")
    if re.search(r"(?i)Hemoglobin|\bHb\b", text) and _web_num(labs, "HGB") is None:
        flags.append("missing_core:HGB")
    for k in ("MCV", "MCH", "MCHC"):
        if re.search(rf"(?i)\b{k}\b", text) and _web_num(labs, k) is None:
            flags.append(f"missing_core:{k}")

    if re.search(r"(?i)Urobilinogen|Tỉ\s*trọng|Phân\s*tích\s*nước\s*tiểu", text):
        # PDF explicitly says no urine sample collected — not a parse miss
        if not re.search(
            r"(?i)Không\s*lấy\s*mẫu|Khong\s*lay\s*mau|không\s*lấy\s*nước\s*tiểu|khong\s*lay\s*nuoc\s*tieu",
            text,
        ):
            urine_n = sum(
                1
                for k in (
                    "Urobilinogen",
                    "Glucose_NT",
                    "Ketone",
                    "Protein_NT",
                    "Nitrite",
                    "pH_NT",
                    "Ti_trong",
                    "Bach_cau_NT",
                    "Mau_NT",
                    "Bilirubin_NT",
                )
                if (labs.get(k) or {}).get("value_raw") not in (None, "")
            )
            if urine_n < 3:
                flags.append(f"missing_urine:n={urine_n}")
    # False Mau_NT year
    mau = (labs.get("Mau_NT") or {}).get("value_raw")
    if mau and re.fullmatch(r"(?:19|20)\d{2}", str(mau)):
        flags.append(f"false_mau_year:{mau}")

    if rbc is not None and rbc > 8:
        flags.append(f"wild_range:RBC={rbc}")
    wbc = _web_num(labs, "WBC")
    if wbc is not None and wbc > 50:
        flags.append(f"wild_range:WBC={wbc}")
    plt = _web_num(labs, "PLT")
    if plt is not None and plt < 20:
        flags.append(f"wild_range:PLT={plt}")

    return flags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--folder", default="", help="Only this folder (absolute or under sync)")
    args = ap.parse_args()

    sync = None
    try:
        cfg = load_config()
        sync = resolve_g_sync(cfg)
    except Exception:
        sync = None

    if args.folder.strip():
        p = Path(args.folder.strip())
        if not p.is_absolute() and sync:
            p = sync / args.folder.strip()
        targets = [(p.name, p)]
    else:
        targets = collect_targets(sync, cwd=ROOT)

    safe_print("========== PARSE AUDIT (no Medinet, no move) ==========")
    safe_print(f"SYNC={sync}")
    pdfs: list[tuple[str, Path]] = []
    for label, d in targets:
        if not d.exists():
            safe_print(f"  skip missing: {label}")
            continue
        found = sorted(d.rglob("*.pdf"))
        safe_print(f"  {label}: {len(found)} pdf")
        for pdf in found:
            pdfs.append((label, pdf))
    if args.limit > 0:
        pdfs = pdfs[: args.limit]
        safe_print(f"Limited: {len(pdfs)}")

    flag_counts: Counter[str] = Counter()
    bad_rows: list[str] = []
    n_ok = 0
    for i, (label, pdf) in enumerate(pdfs, 1):
        flags = audit_one(pdf)
        if not flags:
            n_ok += 1
        else:
            for f in flags:
                kind = f.split(":")[0]
                flag_counts[kind] += 1
            line = f"{label}\t{pdf.name}\t{';'.join(flags)}"
            bad_rows.append(line)
            if len(bad_rows) <= 40 or any(
                f.startswith(("sci9", "sci12")) for f in flags
            ):
                safe_print(f"  BAD [{i}/{len(pdfs)}] {pdf.name}: {flags}")
        if i % 100 == 0:
            safe_print(f"  … {i}/{len(pdfs)} ok={n_ok} bad={len(bad_rows)}")

    build = ROOT / "pipeline" / "work" / "build" / "logs"
    build.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = build / f"PARSE_AUDIT_{stamp}.txt"
    with out.open("w", encoding="utf-8") as fh:
        fh.write(f"total={len(pdfs)} ok={n_ok} bad={len(bad_rows)}\n")
        fh.write(f"flags={dict(flag_counts)}\n")
        fh.write("---\n")
        for row in bad_rows:
            fh.write(row + "\n")
    safe_print(f"DONE total={len(pdfs)} ok={n_ok} bad={len(bad_rows)} flags={dict(flag_counts)}")
    safe_print(f"LOG={out}")
    # Fail hard if legacy 10^ bug still present
    if flag_counts.get("sci9") or flag_counts.get("sci12"):
        safe_print("FAIL: sci9/sci12 still present after fix")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
