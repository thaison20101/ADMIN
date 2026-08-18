"""Unit tests: strict TTHC match (full name + year + gender + phone)."""
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


def test_names_reject_partial():
    assert _names_soft_match("TRẦN SANH", "TRẦN SANH")
    assert not _names_soft_match("TRẦN SANH", "TRẦN NGỌC SANH")
    assert not _names_soft_match("TRẦN SANH", "TRẦN VĂN SANH")
    assert not _names_soft_match("NGUYỄN THỊ THƠM", "NGUYỄN VĂN THƠM")
    assert _names_soft_match("NGUYỄN THỊ THƠM", "NGUYEN THI THOM")
    assert not _names_soft_match("NGUYỄN THỊ KIỀU", "NGUYỄN THỊ KIỀU DIỄM")


def test_gender_and_phone():
    assert _norm_gender("Nam") == "M"
    assert _norm_gender("Nữ") == "F"
    assert _norm_gender("F") == "F"
    assert _phones_match("0767 710 211", "0767710211")
    assert not _phones_match("0767710211", "0937309977")
    assert not _phones_match(".", "0776734159")  # PDF junk phone → no digits


def test_tran_sanh_not_tran_ngoc_sanh():
    idx = _empty_index()
    wrong = {
        "HoTen": "TRẦN NGỌC SANH",
        "NgaySinh": "11/03/1966",
        "GioiTinh": "Nam",
        "SDT": "0776734159",
        "phieukhamId": 111,
        "Id": 111,
        "_mau": "M4",
    }
    idx["by_fold_year"]["TRAN NGOC SANH|1966"] = [wrong]
    idx["by_name_year"]["TRẦN NGỌC SANH|1966"] = [wrong]
    idx["by_phone"]["0776734159"] = [wrong]
    idx["no_cls_ids"].add(111)

    row = {
        "ho_ten": "TRẦN SANH",
        "nam_sinh": "1966",
        "gioi_tinh": "Nam",
        "sdt": ".",
        "file_name": "070826-485689 - TRAN SANH - 1966 - M.pdf",
    }
    st, rec = match_patient(row, idx)
    assert st == "WAITING_ADMIN", st
    assert rec is None


def test_thi_thom_not_van_thom():
    idx = _empty_index()
    wrong = {
        "HoTen": "NGUYỄN VĂN THƠM",
        "NgaySinh": "06/08/1955",
        "GioiTinh": "Nam",
        "SDT": "0937309977",
        "phieukhamId": 222,
        "Id": 222,
        "_mau": "M4",
    }
    idx["by_fold_year"]["NGUYEN VAN THOM|1955"] = [wrong]
    idx["by_name_year"]["NGUYỄN VĂN THƠM|1955"] = [wrong]
    idx["by_phone"]["0937309977"] = [wrong]
    idx["no_cls_ids"].add(222)

    row = {
        "ho_ten": "NGUYỄN THỊ THƠM",
        "nam_sinh": "1955",
        "gioi_tinh": "Nữ",
        "sdt": "0767 710 211",
        "file_name": "070826-487184-NGUYEN THI THOM-1955 - F.pdf",
    }
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
        "gioi_tinh": "Nữ",
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
    # 108 days inclusive → 8 windows of 14d
    assert len(chunks) == 8, len(chunks)
    assert chunks[0][0] == d0
    assert chunks[-1][1] == d1
    n = 0
    for a, b in chunks:
        n += (b - a).days + 1
        assert (b - a).days + 1 <= 14
    assert n == (d1 - d0).days + 1


if __name__ == "__main__":
    test_names_reject_partial()
    test_gender_and_phone()
    test_tran_sanh_not_tran_ngoc_sanh()
    test_thi_thom_not_van_thom()
    test_exact_match_ok()
    test_daterange_chunks()
    from pipeline.parse_cycle_stats import parse as parse_stats

    s = parse_stats("Done: {'imported': 103, 'queued': 0, 'imported_partial_to_error': 2}")
    assert s["imported"] == 103 and s["partial"] == 2

    from pipeline.restore_processed_from_missing import should_restore

    assert should_restore({"status": "IMPORTED", "notes": "imported_full:ok"})
    assert should_restore({"status": "WAITING_ADMIN", "notes": "disk_processed_fullrematch:IMPORTED"})
    assert not should_restore({"status": "WAITING_ADMIN", "notes": "no_tthc_match"})
    print("OK: all strict-match tests passed")
