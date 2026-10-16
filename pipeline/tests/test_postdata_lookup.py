"""Unit tests: PostDataWithDataOutput patient lookup (no ExecuteStore)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

import medinet_api as api  # noqa: E402


def test_lookup_by_cccd_unique():
    meta = {"id": 1002176, "sqlContent": "x", "dataSourceId": 1}
    row = {
        "Id": 555,
        "phieukhamId": 555,
        "HoTen": "CHAU THI THANH TUYEN",
        "NgaySinh": "11/09/1999",
        "CCCD": "084199009358",
    }

    with (
        patch.object(api, "_get_report_meta", return_value=meta),
        patch.object(
            api, "postdata_fetch_page", return_value=([row], 200, "tok")
        ),
    ):
        rec, det, tok = api.lookup_tthc_by_name_cccd(
            "tok",
            name="CHAU THI THANH TUYEN",
            cccd="084199009358",
            year="1999",
            date_from="01/07/2026",
            date_to="16/10/2026",
        )
    assert rec is not None
    assert int(rec["phieukhamId"]) == 555
    assert "postdata_unique" in det


def test_lookup_denied():
    meta = {"id": 1002176}
    with (
        patch.object(api, "_get_report_meta", return_value=meta),
        patch.object(api, "postdata_fetch_page", return_value=([], 403, "tok")),
    ):
        rec, det, tok = api.lookup_tthc_by_name_cccd(
            "tok", name="A", cccd="", year="1990"
        )
    assert rec is None
    assert "denied" in det.lower() or "403" in det


def test_lookup_no_name_or_cccd():
    rec, det, tok = api.lookup_tthc_by_name_cccd("tok", name="", cccd="")
    assert rec is None
    assert det == "no_name_or_cccd"


def test_probe_fill_includes_postdata():
    with (
        patch.object(api, "probe_drviewer_access", return_value=(False, "403")),
        patch.object(api, "probe_postdata_access", return_value=(True, "http=200")),
        patch.object(api, "probe_formviewer_cls", return_value=(True, "http=200")),
    ):
        caps = api.probe_fill_capabilities({"tk1": "t"})
    assert caps["postdata_ok"] is True
    assert caps["formviewer_ok"] is True
    assert caps["drviewer_ok"] is False


if __name__ == "__main__":
    test_lookup_by_cccd_unique()
    test_lookup_denied()
    test_lookup_no_name_or_cccd()
    test_probe_fill_includes_postdata()
    print("POSTDATA_LOOKUP_OK")
