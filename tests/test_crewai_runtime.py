import sysconfig
from pathlib import Path

import crewai


def test_crewai_imports_from_embedded_runtime():
    runtime_path = Path(crewai.__file__).resolve()
    site_packages = Path(sysconfig.get_paths()["purelib"]).resolve()
    vendor_path = Path(__file__).resolve().parents[1] / "crewAI"

    assert runtime_path.is_file()
    assert runtime_path.is_relative_to(site_packages)
    assert not runtime_path.is_relative_to(vendor_path)
    assert crewai.__version__ == "1.15.32"
