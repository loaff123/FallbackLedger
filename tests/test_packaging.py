import importlib.util
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def checker():
    spec = importlib.util.spec_from_file_location(
        "check_installed", ROOT / "tools" / "check_installed.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_archive_audit_rejects_third_party_data_and_private_state(tmp_path):
    archive = tmp_path / "bad.whl"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("fallbackledger/simcheck.dta", b"data")
    with pytest.raises(ValueError, match="disallowed"):
        checker().audit_archive(archive)


def test_archive_audit_accepts_original_package_code(tmp_path):
    archive = tmp_path / "tiny.whl"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("fallbackledger/__init__.py", "")
    assert checker().audit_archive(archive) == ["fallbackledger/__init__.py"]
