"""Unit tests: TTHC match (ho+ten + year — rule truoc khi siết strict)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import date

from pipeline.phase_b_preview import (  # noqa: E402
    _daterange_chunks,
    _names_soft_match,
    _norm_gender,
    _phones_match,
    match_patient,
)


def _empty_index() -> dict:
    return {
        "by_phone": {},
        "by_name_year": {},
        "by_fold_year": {},
        "by_cccd": {},
        "by_maphieu": {},
        "by_pid": {},
        "no_cls_ids": set(),
        "all_ids": set(),
    }


def test_names_ho_ten_rule():
    """Rule cu: cung ho (token dau) + cung ten (token cuoi); giua co the khac."""
    assert _names_soft_match("TRẦN SANH", "TRẦN SANH")
    assert _names_soft_match("TRẦN SANH", "TRẦN NGỌC SANH")
    assert _names_soft_match("TRẦN SANH", "TRẦN VĂN SANH")
    assert _names_soft_match("NGUYỄN THỊ THƠM", "NGUYỄN VĂN THƠM")
    assert _names_soft_match("NGUYỄN THỊ THƠM", "NGUYEN THI THOM")
    assert not _names_soft_match("NGUYỄN THỊ KIỀU", "NGUYỄN THỊ KIỀU DIỄM")


def test_gender_and_phone_helpers():
    assert _norm_gender("Nam") == "M"
    assert _norm_gender("Nữ") == "F"
    assert _phones_match("0767 710 211", "0767710211")
    assert not _phones_match("0767710211", "0937309977")
    assert not _phones_match(".", "0776734159")


def test_tran_sanh_matches_tran_ngoc_sanh_old_rule():
    """Rule cu chap nhan vai ca sai (TRAN SANH ~ TRAN NGOC SANH) de khop ~8000 file."""
    idx = _empty_index()
    rec = {
        "HoTen": "TRẦN NGỌC SANH",
        "NgaySinh": "11/03/1966",
        "GioiTinh": "Nam",
        "SDT": "0776734159",
        "phieukhamId": 111,
        "Id": 111,
        "_mau": "M4",
    }
    idx["by_fold_year"]["TRAN NGOC SANH|1966"] = [rec]
    idx["by_name_year"]["TRẦN NGỌC SANH|1966"] = [rec]
    idx["no_cls_ids"].add(111)

    row = {
        "ho_ten": "TRẦN SANH",
        "nam_sinh": "1966",
        "file_name": "070826-485689 - TRAN SANH - 1966 - M.pdf",
        "mau_kham": "M4",
    }
    st, got = match_patient(row, idx)
    assert st == "READY_IMPORT", st
    assert got and got.get("phieukhamId") == 111


def test_thi_thom_matches_van_thom_old_rule():
    idx = _empty_index()
    rec = {
        "HoTen": "NGUYỄN VĂN THƠM",
        "NgaySinh": "06/08/1955",
        "GioiTinh": "Nam",
        "SDT": "0937309977",
        "phieukhamId": 222,
        "Id": 222,
        "_mau": "M4",
    }
    idx["by_fold_year"]["NGUYEN VAN THOM|1955"] = [rec]
    idx["by_name_year"]["NGUYỄN VĂN THƠM|1955"] = [rec]
    idx["no_cls_ids"].add(222)

    row = {
        "ho_ten": "NGUYỄN THỊ THƠM",
        "nam_sinh": "1955",
        "file_name": "070826-487184-NGUYEN THI THOM-1955 - F.pdf",
        "mau_kham": "M4",
    }
    st, got = match_patient(row, idx)
    assert st == "READY_IMPORT", st
    assert got and got.get("phieukhamId") == 222


def test_kieu_not_kieu_diem():
    idx = _empty_index()
    wrong = {
        "HoTen": "NGUYỄN THỊ KIỀU DIỄM",
        "NgaySinh": "01/01/1990",
        "phieukhamId": 999,
        "Id": 999,
        "_mau": "M3",
    }
    idx["by_fold_year"]["NGUYEN THI KIEU DIEM|1990"] = [wrong]
    idx["no_cls_ids"].add(999)
    row = {"ho_ten": "NGUYỄN THỊ KIỀU", "nam_sinh": "1990", "mau_kham": "M3"}
    st, rec = match_patient(row, idx)
    assert st == "WAITING_ADMIN", st
    assert rec is None


def test_exact_match_ok():
    idx = _empty_index()
    ok = {
        "HoTen": "NGUYỄN THỊ THƠM",
        "NgaySinh": "01/01/1955",
        "GioiTinh": "Nữ",
        "SDT": "0767710211",
        "phieukhamId": 333,
        "Id": 333,
        "MaPhieu": "KSKDKP333",
        "_mau": "M4",
    }
    idx["by_fold_year"]["NGUYEN THI THOM|1955"] = [ok]
    idx["by_name_year"]["NGUYỄN THỊ THƠM|1955"] = [ok]
    idx["by_phone"]["0767710211"] = [ok]
    idx["no_cls_ids"].add(333)

    row = {
        "ho_ten": "NGUYỄN THỊ THƠM",
        "nam_sinh": "1955",
        "sdt": "0767710211",
        "file_name": "070826-487184-NGUYEN THI THOM-1955 - F.pdf",
        "mau_kham": "M4",
    }
    st, rec = match_patient(row, idx)
    assert st == "READY_IMPORT", st
    assert rec and rec.get("phieukhamId") == 333


def test_daterange_chunks():
    d0 = date(2026, 5, 2)
    d1 = date(2026, 8, 17)
    chunks = _daterange_chunks(d0, d1, chunk_days=14)
    assert len(chunks) == 8, len(chunks)
    assert chunks[0][0] == d0
    assert chunks[-1][1] == d1


if __name__ == "__main__":
    test_names_ho_ten_rule()
    test_gender_and_phone_helpers()
    test_tran_sanh_matches_tran_ngoc_sanh_old_rule()
    test_thi_thom_matches_van_thom_old_rule()
    test_kieu_not_kieu_diem()
    test_exact_match_ok()
    test_daterange_chunks()
    from pipeline.parse_cycle_stats import parse as parse_stats

    s = parse_stats("Done: {'imported': 103, 'queued': 0, 'imported_partial_to_error': 2}")
    assert s["imported"] == 103 and s["partial"] == 2

    from pipeline.restore_processed_from_missing import should_restore

    assert should_restore({"status": "IMPORTED", "notes": "imported_full:ok"})
    assert should_restore({"status": "WAITING_ADMIN", "notes": "disk_processed_fullrematch:IMPORTED"})
    assert should_restore(
        {"status": "WAITING_ADMIN", "notes": "no_tthc_match", "source_file": r"G:\x\PROCESSED\a.pdf"}
    )
    assert not should_restore({"status": "WAITING_ADMIN", "notes": "no_tthc_match"})

    def test_best_pipeline_picks_fat_tree():
        import tempfile

        from pipeline.drive_paths import STD_FOLDERS, _best_pipeline_dir

        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "empty"
            fat = Path(td) / "fat"
            for root in (empty, fat):
                for name in STD_FOLDERS:
                    (root / name).mkdir(parents=True)
            (fat / "MISSING" / "a.pdf").write_bytes(b"%PDF")
            (fat / "INBOX_CLS" / "b.pdf").write_bytes(b"%PDF")
            picked = _best_pipeline_dir([empty, fat])
            assert picked.resolve() == fat.resolve(), picked

    test_best_pipeline_picks_fat_tree()
    from pipeline.drive_paths import (
        _first_existing_dir,
        PINNED_PIPELINE,
        discover_build_root,
        is_forbidden_d_pipeline,
        resolve_g_sync,
    )

    assert callable(_first_existing_dir)
    assert "PKDK_Thuankieu_Pipeline" in str(PINNED_PIPELINE)
    assert is_forbidden_d_pipeline(r"D:\PKDK_Thuankieu_Pipeline")
    build_dir = discover_build_root({})
    bs = str(build_dir).replace("\\", "/")
    assert bs.endswith("pipeline/work/build") or "/pipeline/work/build" in bs, build_dir

    # Fallback must never resolve to ADMIN repo / D: even if config says so
    bad_cfg = {
        "drive": {
            "local_sync_root": r"C:\Users\thais\ADMIN",
        }
    }
    sync_bad = resolve_g_sync(bad_cfg)
    su = str(sync_bad).replace("/", "\\").upper()
    assert not su.rstrip("\\").endswith("ADMIN"), sync_bad
    assert not su.startswith("D:"), sync_bad

    d_cfg = {"drive": {"local_sync_root": r"D:\PKDK_Thuankieu_Pipeline"}}
    sync_d = resolve_g_sync(d_cfg)
    assert not str(sync_d).replace("/", "\\").upper().startswith("D:"), sync_d

    # Windows + G: dead: pin G:, never ADMIN even when config points there
    import sys as _sys
    import pipeline.drive_paths as _dp

    _real_plat = _sys.platform
    _orig_live = _dp.g_pipeline_live
    _sys.platform = "win32"
    _dp.g_pipeline_live = lambda: None
    try:
        pinned = _dp.resolve_g_sync(bad_cfg)
        assert str(pinned) == str(_dp.PINNED_PIPELINE), pinned
        pinned_d = _dp.resolve_g_sync(d_cfg)
        assert str(pinned_d) == str(_dp.PINNED_PIPELINE), pinned_d
    finally:
        _dp.g_pipeline_live = _orig_live
        _sys.platform = _real_plat

    from pipeline.auto_cycle import _collect_scan_dirs, _row_priority
    from pathlib import Path as _P

    def test_repair_skips_missing():
        inbox, miss, err, proc = _P("INBOX_CLS"), _P("MISSING"), _P("ERROR"), _P("PROCESSED")
        dirs = _collect_scan_dirs(
            _P("sync"), inbox, miss, err, proc, full_scan=False, repair=True
        )
        assert miss not in dirs
        assert inbox in dirs and err in dirs and proc in dirs

    test_repair_skips_missing()

    def test_hourly_scan_skips_missing_walk():
        inbox, miss, err, proc = _P("INBOX_CLS"), _P("MISSING"), _P("ERROR"), _P("PROCESSED")
        dirs = _collect_scan_dirs(
            _P("sync"), inbox, miss, err, proc, full_scan=False, repair=False
        )
        assert miss not in dirs, dirs
        assert inbox in dirs and err in dirs
        assert proc not in dirs

    test_hourly_scan_skips_missing_walk()

    def test_count_pdfs_fast_top_level(tmp_path=None):
        import tempfile
        from pipeline.drive_paths import count_pdfs_fast

        with tempfile.TemporaryDirectory() as d:
            root = _P(d)
            (root / "a.pdf").write_bytes(b"%PDF")
            (root / "b.PDF").write_bytes(b"%PDF")
            (root / "note.txt").write_text("x")
            sub = root / "sub"
            sub.mkdir()
            (sub / "c.pdf").write_bytes(b"%PDF")
            n = count_pdfs_fast(root)
            assert n == 3, n  # top-level 2 + one extra folder 1

    test_count_pdfs_fast_top_level()

    from pipeline.auto_cycle import counts_from_rows, format_counts_line

    def test_counts_from_rows():
        rows = [
            {"source_file": r"G:\Drive của tôi\PKDK_Thuankieu_Pipeline\INBOX_CLS\a.pdf"},
            {"source_file": r"G:\x\MISSING\b.pdf"},
            {"source_file": r"G:\x\MISSING\c.pdf"},
            {"source_file": r"G:\x\ERROR\d.pdf"},
            {"source_file": r"G:\x\PROCESSED\e.pdf"},
        ]
        c = counts_from_rows(rows)
        assert c["inbox"] == 1 and c["missing"] == 2 and c["error"] == 1 and c["processed"] == 1, c
        line = format_counts_line(c)
        assert "missing=2" in line and line.startswith("COUNTS\t"), line

    test_counts_from_rows()

    def test_inbox_before_missing():
        inbox = {
            "status": "READY_IMPORT",
            "source_file": r"G:\Drive của tôi\PKDK_Thuankieu_Pipeline\INBOX_CLS\a.pdf",
        }
        miss = {
            "status": "WAITING_ADMIN",
            "source_file": r"G:\Drive của tôi\PKDK_Thuankieu_Pipeline\MISSING\c.pdf",
        }
        rows = [miss] * 20 + [inbox]
        order = sorted(range(len(rows)), key=lambda i: (_row_priority(rows[i]), i))
        assert rows[order[0]] is inbox

    test_inbox_before_missing()

    def test_runner_ps1_ascii():
        root = Path(__file__).resolve().parent
        for name in (
            "CHAY_REMATCH_MISSING.ps1",
            "CHAY_GAP_ROI_HOURLY.ps1",
            "CHAY_BO_SUNG_THIEU.ps1",
            "run_hourly.ps1",
        ):
            (root / name).read_bytes().decode("ascii")

    test_runner_ps1_ascii()
    print("OK: all match tests passed")
