"""Load the operational scripts in scripts/ (they are not part of the app package) for testing."""

import importlib.util
import sys
from types import ModuleType

from app.core.config import REPO_ROOT

SCRIPTS = REPO_ROOT / "scripts"


def load_script(name: str) -> ModuleType:
    module_name = f"siteguard_script_{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module
