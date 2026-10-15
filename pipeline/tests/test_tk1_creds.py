"""Assert TK1 credentials; TK2 skipped by default."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from medinet_creds import (  # noqa: E402
    MEDINET_ACCOUNTS,
    get_medinet_accounts,
    tk2_enabled,
)


def test_tk1_creds():
    a = MEDINET_ACCOUNTS[0]
    assert a["user"] == "pkdkthuankieu"
    assert a["password"] == "Qlskcd@2026"
    # Default: skip TK2
    os.environ.pop("MEDINET_ENABLE_TK2", None)
    assert tk2_enabled() is False
    got = get_medinet_accounts()
    assert len(got) == 1
    assert got[0]["user"] == "pkdkthuankieu"
    assert got[0]["password"] == "Qlskcd@2026"
    # Opt-in TK2
    os.environ["MEDINET_ENABLE_TK2"] = "1"
    try:
        got2 = get_medinet_accounts()
        assert len(got2) == 2
        assert got2[1]["user"] == "pkdk_Thuankieu"
    finally:
        os.environ.pop("MEDINET_ENABLE_TK2", None)


if __name__ == "__main__":
    test_tk1_creds()
    print("CREDS_OK pkdkthuankieu / Qlskcd@2026 (TK2 skipped)")
