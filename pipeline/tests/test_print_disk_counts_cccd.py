"""print_disk_counts must include CCCD without KeyError."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PIPE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPE))

from drive_paths import EXTRA_FOLDERS, STD_FOLDERS, UNDER18_FOLDER  # noqa: E402
import print_disk_counts as pdc  # noqa: E402


def test_extra_folders_includes_cccd():
    assert "CCCD" in EXTRA_FOLDERS


def test_key_for_all_std_and_extra():
    for name in list(STD_FOLDERS) + list(EXTRA_FOLDERS):
        key = pdc._key_for(name)
        assert key
        assert " " not in key


def test_disk_counts_handles_cccd(tmp_path):
    sync = tmp_path / "Gpipe"
    for name in list(STD_FOLDERS) + list(EXTRA_FOLDERS):
        (sync / name).mkdir(parents=True, exist_ok=True)
    build = tmp_path / "build"
    build.mkdir(exist_ok=True)

    def fake_folders(pipeline, build_root):
        return {n: pipeline / n for n in list(STD_FOLDERS) + list(EXTRA_FOLDERS)}

    with (
        patch.object(pdc, "discover_pipeline_root", return_value=sync),
        patch.object(pdc, "discover_build_root", return_value=build),
        patch.object(pdc, "ensure_standard_folders", side_effect=fake_folders),
        patch.object(pdc, "count_pdfs_fast", return_value=3),
    ):
        c = pdc.disk_counts(sync)
    assert c["cccd"] == 3
    assert c["inbox"] == 3
    # Simulates the crash path: iterating STD+EXTRA then indexing
    for name in list(STD_FOLDERS) + list(EXTRA_FOLDERS):
        key = pdc._key_for(name)
        assert key in c


if __name__ == "__main__":
    import tempfile

    test_extra_folders_includes_cccd()
    test_key_for_all_std_and_extra()
    with tempfile.TemporaryDirectory() as td:
        test_disk_counts_handles_cccd(Path(td))
    print("OK")
