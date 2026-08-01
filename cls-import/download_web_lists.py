#!/usr/bin/env python3
import os
"""Download M3/M4 patient lists from Medinet for matching against PDF results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from medinet_client import MedinetClient

OUT = Path("/workspace/build for BIG DATA")

M3 = {
    "report_id": 1002176,
    "code": "KSKDK_DanhSach_KSK_M13",
    "date_key": "NgayTao",
}
M4 = {
    "report_id": 1002181,
    "code": "KSKDK_DanhSach_KSK_NguoiCaoTuoi_Report",
    "date_key": "KSKDK_NgayKham",
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", default="pkdkthuankieu")
    p.add_argument("--password", default=os.environ.get("MEDINET_PASSWORD",""))
    p.add_argument("--date-from", default="01/04/2026")
    p.add_argument("--date-to", default="31/08/2026")
    args = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    client = MedinetClient(args.user, args.password)
    date_range = f"{args.date_from} - {args.date_to}"

    # M3
    print("Downloading M3...")
    m3_filters = {
        "KSKDK_HoVaTen": None,
        "KSKDK_DinhDanhCaNhan": None,
        "KSKDK_TramYTe": None,
        "NgayTao": date_range,
        "ChatLuongDuLieu": None,
        "DoiTuongKham": None,
        "HinhThucChiTra": None,
        "HinhThucKham": None,
    }
    m3 = client.fetch_all(M3["report_id"], M3["code"], m3_filters, page_size=100)
    (OUT / "web_list_M3.json").write_text(json.dumps(m3, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"M3 saved: {len(m3)}")

    # M4
    print("Downloading M4...")
    m4_filters = {
        "KSKDK_HoVaTen": None,
        "KSKDK_DinhDanhCaNhan": None,
        "KSKDK_TramYTe": None,
        "KSKDK_NgayKham": date_range,
        "IsDaKham": None,
        "ChatLuongDuLieu": None,
    }
    m4 = client.fetch_all(M4["report_id"], M4["code"], m4_filters, page_size=100)
    (OUT / "web_list_M4.json").write_text(json.dumps(m4, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"M4 saved: {len(m4)}")

    summary = {"m3": len(m3), "m4": len(m4), "date_range": date_range}
    (OUT / "web_list_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
