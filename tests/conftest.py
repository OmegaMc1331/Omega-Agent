from __future__ import annotations

import getpass
import os
import shutil
import tempfile
import time
from pathlib import Path

_MANAGED_BASETEMP: Path | None = None


def pytest_configure(config) -> None:
    global _MANAGED_BASETEMP

    if config.option.basetemp is not None:
        requested = Path(config.option.basetemp).expanduser().resolve()
        if _remove_noncritical_temp_tree(requested):
            _MANAGED_BASETEMP = requested
        else:
            _MANAGED_BASETEMP = Path(tempfile.mkdtemp(prefix="omega-agent-pytest-"))
            config.option.basetemp = str(_MANAGED_BASETEMP)
        return
    default_root = Path(tempfile.gettempdir()) / f"pytest-of-{getpass.getuser()}"
    try:
        default_root.mkdir(mode=0o700, exist_ok=True)
        with os.scandir(default_root):
            pass
    except OSError:
        _MANAGED_BASETEMP = Path(tempfile.mkdtemp(prefix="omega-agent-pytest-"))
        config.option.basetemp = str(_MANAGED_BASETEMP)


def pytest_unconfigure(config) -> None:
    if _MANAGED_BASETEMP is not None:
        _remove_noncritical_temp_tree(_MANAGED_BASETEMP)


def _remove_noncritical_temp_tree(path: Path) -> bool:
    for delay in (0.05, 0.15, 0.3):
        try:
            shutil.rmtree(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            time.sleep(delay)
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.lexists(path)
