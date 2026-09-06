import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _detect_version() -> str:
    try:
        return version("f1-live-copilot")
    except PackageNotFoundError:
        pass
    # Dev scripts with inline metadata import the checkout via sys.path, where no dist-info exists.
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.M)
    except OSError:
        return "unknown"
    return match.group(1) if match else "unknown"


__version__ = _detect_version()

__all__ = ["__version__"]
