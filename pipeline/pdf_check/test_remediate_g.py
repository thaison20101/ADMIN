"""Unit tests for remediate_g + inbox dedup (no Medinet / no G:)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPE = ROOT / "pipeline"
sys.path.insert(0, str(PIPE))
sys.path.insert(0, str(PIPE / "pdf_check"))


def test_remediate_scan_order():
    from remediate_g import REMEDIATE_FOLDERS, build_process_queue

    assert REMEDIATE_FOLDERS == ("PROCESSED", "MISSING", "UNDER 18", "TK1", "TK2")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name in REMEDIATE_FOLDERS:
            (root / name).mkdir()
        dup = "140826-1 - NGUYEN KHAC HOANG - 1990 - M.pdf"
        (root / "MISSING" / dup).write_bytes(b"%PDF-a")
        (root / "PROCESSED" / dup).write_bytes(b"%PDF-b")
        (root / "TK1" / "other.pdf").write_bytes(b"%PDF-c")
        q = build_process_queue(root, REMEDIATE_FOLDERS)
        assert len(q) == 2
        assert q[0]["folder"] == "PROCESSED"
        assert q[0]["file_name"] == dup


def test_decide_target_filled_ok_gate():
    from remediate_g import decide_target_folder

    assert (
        decide_target_folder(
            match_status="READY",
            tthc_scope="BOTH",
            coverage="FULL",
            sample_kind="BLOOD_URINE",
            filled_ok=2,
            n_accts=2,
            cls_tk1="YES",
            cls_tk2="YES",
            primary_account="pkdkthuankieu",
        )
        == "PROCESSED"
    )
    assert (
        decide_target_folder(
            match_status="READY",
            tthc_scope="BOTH",
            coverage="FULL",
            sample_kind="BLOOD_URINE",
            filled_ok=1,
            n_accts=2,
            cls_tk1="YES",
            cls_tk2="NO",
            primary_account="pkdkthuankieu",
        )
        == "TK1"
    )
    assert (
        decide_target_folder(
            match_status="READY",
            tthc_scope="BOTH",
            coverage="FULL",
            sample_kind="BLOOD_URINE",
            filled_ok=1,
            n_accts=2,
            cls_tk1="NO",
            cls_tk2="YES",
            primary_account="pkdk_Thuankieu",
        )
        == "TK2"
    )


def test_dedupe_delete_others():
    from remediate_g import dedupe_delete_others

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name in ("PROCESSED", "MISSING", "TK1"):
            (root / name).mkdir()
        name = "dup.pdf"
        keep = root / "PROCESSED" / name
        miss = root / "MISSING" / name
        tk = root / "TK1" / name
        keep.write_bytes(b"a")
        miss.write_bytes(b"b")
        tk.write_bytes(b"c")
        deleted = dedupe_delete_others(root, keep, name, apply=True)
        assert len(deleted) == 2
        assert keep.exists()
        assert not miss.exists()
        assert not tk.exists()


def test_inbox_dup_hold_root():
    from dedup import hold_inbox_duplicate_at_root, inbox_duplicate_exists

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "INBOX_CLS").mkdir()
        (root / "PROCESSED").mkdir()
        name = "same.pdf"
        inbox_pdf = root / "INBOX_CLS" / name
        (root / "PROCESSED" / name).write_bytes(b"x")
        inbox_pdf.write_bytes(b"y")
        assert inbox_duplicate_exists(root, name, exclude=inbox_pdf)
        moved = hold_inbox_duplicate_at_root(inbox_pdf, root, dry_run=False)
        assert moved is not None
        assert moved.parent == root
        assert not inbox_pdf.exists()
