from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPE = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(PIPE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from move_under18 import is_under18  # noqa: E402


class MoveUnder18Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.as_of = date(2026, 8, 21)

    def test_year_cutoff(self) -> None:
        # Age 17 in 2026 => born 2009 => under18
        self.assertTrue(is_under18(nam_sinh="2009", file_name="x.pdf", as_of=self.as_of))
        # Age 18 in 2026 => born 2008 => adult
        self.assertFalse(is_under18(nam_sinh="2008", file_name="x.pdf", as_of=self.as_of))
        self.assertFalse(is_under18(nam_sinh="1990", file_name="x.pdf", as_of=self.as_of))

    def test_filename_mau_m1_m2_m12(self) -> None:
        self.assertTrue(
            is_under18(
                nam_sinh="",
                file_name="010725-1 - BE NAM - M2.pdf",
                as_of=self.as_of,
            )
        )
        self.assertTrue(
            is_under18(
                nam_sinh="",
                file_name="010725-1 - BE NAM - M12.pdf",
                as_of=self.as_of,
            )
        )
        self.assertTrue(
            is_under18(
                nam_sinh="",
                file_name="Nguyen Van A_01_01_2015_Nam_M1.pdf",
                as_of=self.as_of,
            )
        )

    def test_adult_not_flagged(self) -> None:
        self.assertFalse(
            is_under18(
                nam_sinh="1990",
                file_name="010725-1 - ONG A - 1950 - M.pdf",
                as_of=self.as_of,
            )
        )
        self.assertFalse(
            is_under18(
                nam_sinh="",
                file_name="010725-1 - ONG A - 1950 - M.pdf",
                as_of=self.as_of,
            )
        )


if __name__ == "__main__":
    unittest.main()
