"""Assert TK1 credentials match may-A expected login."""
from __future__ import annotations

import sys
from pathlib import Path

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from medinet_creds import MEDINET_ACCOUNTS, get_medinet_accounts  # noqa: E402


def test_tk1_creds():
    a = MEDINET_ACCOUNTS[0]
    assert a["user"] == "pkdkthuankieu"
    assert a["password"] == "Qlskcd@2026"
    got = get_medinet_accounts()
    assert got[0]["user"] == "pkdkthuankieu"
    assert got[0]["password"] == "Qlskcd@2026"
    # TK2 unchanged
    assert got[1]["user"] == "pkdk_Thuankieu"


if __name__ == "__main__":
    test_tk1_creds()
    print("CREDS_OK pkdkthuankieu / Qlskcd@2026")
