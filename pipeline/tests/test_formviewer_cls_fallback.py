"""Unit tests: DRViewer 403 → FormViewer Insert/Update light path."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

import medinet_api as api  # noqa: E402


def _denied_set(token, payload, reauth=None):
    return (
        False,
        "Access denied",
        {"_access_denied": True, "http": 403},
        token,
    )


def _ok_set(token, payload, reauth=None):
    return True, "SET ok", {"isSucceeded": True}, token


def test_access_denied_helper():
    assert api._is_access_denied(403, {"error": {"message": "x"}})
    assert api._is_access_denied(200, None, "Access denied")
    assert not api._is_access_denied(200, {"result": {"isSucceeded": True}}, "ok")


def test_formviewer_soft_ok_versiontype3():
    ok, msg, res = api._formviewer_write_result(
        200,
        {
            "result": {
                "isSucceeded": False,
                "code": "VersionType-3-Non-Insert-Id",
                "message": "no id",
            }
        },
    )
    assert ok is True
    assert "soft-ok" in msg
    assert res.get("code") == "VersionType-3-Non-Insert-Id"


def test_insert_cls_falls_back_on_set_403_update_first():
    payload = {
        "phieukhamId": 12345,
        "LoaiKham": 5152,
        "CongThucMau_SLBC": 5.5,
    }
    calls = {"insert": 0, "update": 0, "set": 0}

    def fake_set(token, pl, reauth=None):
        calls["set"] += 1
        return _denied_set(token, pl, reauth)

    def fake_insert(token, pl, reauth=None):
        calls["insert"] += 1
        return False, "should not need insert", {}, token

    def fake_update(token, pl, reauth=None):
        calls["update"] += 1
        return True, "updated", {"isSucceeded": True}, token

    with (
        patch.object(api, "_set_cls", side_effect=fake_set),
        patch.object(api, "_formviewer_insert_cls", side_effect=fake_insert),
        patch.object(api, "_formviewer_update_cls", side_effect=fake_update),
    ):
        ok, msg, raw, tok = api.insert_cls("tok", payload)

    assert ok is True
    assert msg.startswith("UPDATE-fallback:")
    assert calls["set"] == 1
    assert calls["update"] == 1
    assert calls["insert"] == 0


def test_insert_cls_insert_when_update_fails():
    payload = {"phieukhamId": 99, "CongThucMau_SLBC": 4.1}
    calls = {"insert": 0, "update": 0}

    def fake_insert(token, pl, reauth=None):
        calls["insert"] += 1
        return True, "inserted", {"isSucceeded": True}, token

    def fake_update(token, pl, reauth=None):
        calls["update"] += 1
        return False, "no row", {}, token

    with (
        patch.object(api, "_set_cls", side_effect=_denied_set),
        patch.object(api, "_formviewer_insert_cls", side_effect=fake_insert),
        patch.object(api, "_formviewer_update_cls", side_effect=fake_update),
    ):
        ok, msg, raw, tok = api.insert_cls("tok", payload)

    assert ok is True
    assert msg.startswith("INSERT-fallback:")
    assert calls["update"] == 1
    assert calls["insert"] == 1


def test_prepare_formviewer_mirrors_luc_doi_to_duong_mau():
    pl = api._prepare_formviewer_payload(
        {"phieukhamId": 1, "SinhHoaMau_DuongMauLucDoi": 5.1}
    )
    assert pl["SinhHoaMau_DuongMau"] == 5.1
    assert pl["SinhHoaMau_DuongMauLucDoi"] == 5.1


def test_glucose_twin_accepts_duong_mau_for_luc_doi():
    payload = {"SinhHoaMau_DuongMauLucDoi": 5.1, "CongThucMau_SLBC": 6}
    existing = {"SinhHoaMau_DuongMau": 5.1, "CongThucMau_SLBC": 6}
    miss = api.cls_missing_lab_fields(existing, payload)
    assert "SinhHoaMau_DuongMauLucDoi" not in miss
    assert miss == []


def test_insert_cls_urine_error_does_not_call_formviewer():
    fv_calls = {"n": 0}

    def fake_fv(token, pl, reauth=None):
        fv_calls["n"] += 1
        return True, "nope", {}, token

    # Set always returns urine-format error (never access denied)
    with (
        patch.object(
            api,
            "_set_cls",
            return_value=(False, "Sai dinh dang NuocTieu Negative", {}, "tok"),
        ),
        patch.object(api, "_formviewer_insert_cls", side_effect=fake_fv),
        patch.object(api, "_formviewer_update_cls", side_effect=fake_fv),
    ):
        ok, msg, raw, tok = api.insert_cls(
            "tok",
            {
                "phieukhamId": 1,
                "CongThucMau_SLBC": 5,
                "NuocTieu_Protein": "Negative",
            },
        )

    assert fv_calls["n"] == 0
    assert "INSERT-fallback" not in str(msg)
    assert "UPDATE-fallback" not in str(msg)


def test_insert_cls_set_ok_skips_formviewer():
    fv = {"n": 0}

    def boom(token, pl, reauth=None):
        fv["n"] += 1
        raise AssertionError("FormViewer must not run when Set OK")

    with (
        patch.object(api, "_set_cls", side_effect=_ok_set),
        patch.object(api, "_formviewer_insert_cls", side_effect=boom),
    ):
        ok, msg, raw, tok = api.insert_cls(
            "tok", {"phieukhamId": 7, "CongThucMau_SLBC": 6}
        )
    assert ok is True
    assert msg == "SET ok"
    assert fv["n"] == 0


def test_probe_fill_capabilities_formviewer_only():
    tokens = {"tk1": "t"}

    with (
        patch.object(api, "probe_drviewer_access", return_value=(False, "http=403")),
        patch.object(api, "probe_formviewer_cls", return_value=(True, "http=200 ok")),
    ):
        caps = api.probe_fill_capabilities(tokens)
        out = api.assert_can_fill_or_raise(tokens)

    assert caps["drviewer_ok"] is False
    assert caps["formviewer_ok"] is True
    assert out["formviewer_ok"] is True


def test_assert_can_fill_raises_when_both_denied():
    with (
        patch.object(api, "probe_drviewer_access", return_value=(False, "403")),
        patch.object(api, "probe_formviewer_cls", return_value=(False, "403")),
    ):
        try:
            api.assert_can_fill_or_raise({"tk1": "t"})
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "FormViewer" in str(e) or "DRViewer" in str(e)


if __name__ == "__main__":
    test_access_denied_helper()
    test_formviewer_soft_ok_versiontype3()
    test_insert_cls_falls_back_on_set_403_update_first()
    test_insert_cls_insert_when_update_fails()
    test_prepare_formviewer_mirrors_luc_doi_to_duong_mau()
    test_glucose_twin_accepts_duong_mau_for_luc_doi()
    test_insert_cls_urine_error_does_not_call_formviewer()
    test_insert_cls_set_ok_skips_formviewer()
    test_probe_fill_capabilities_formviewer_only()
    test_assert_can_fill_raises_when_both_denied()
    print("FORMVIEWER_FALLBACK_OK")
