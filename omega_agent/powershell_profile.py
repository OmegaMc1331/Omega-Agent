from __future__ import annotations

import os
import shutil
from pathlib import Path

OMEGA_PROFILE_BEGIN = "# >>> Omega Agent >>>"
OMEGA_PROFILE_END = "# <<< Omega Agent <<<"
LEGACY_PROFILE_BEGIN = "# >>> Omega Agent global command >>>"
LEGACY_PROFILE_END = "# <<< Omega Agent global command <<<"


def omega_profile_block(omega_exe: str | Path) -> str:
    escaped = str(omega_exe).replace("`", "``").replace('"', '`"')
    return "\n".join(
        [
            OMEGA_PROFILE_BEGIN,
            "function omega {",
            f'    & "{escaped}" @args',
            "}",
            OMEGA_PROFILE_END,
        ]
    )


def profile_contains_omega_block(content: str) -> bool:
    return (OMEGA_PROFILE_BEGIN in content and OMEGA_PROFILE_END in content) or (LEGACY_PROFILE_BEGIN in content and LEGACY_PROFILE_END in content)


def profile_contains_omega_function(content: str) -> bool:
    lowered = content.lower()
    return "function omega" in lowered or "function global:omega" in lowered


def replace_or_append_omega_block(content: str, omega_exe: str | Path) -> str:
    block = omega_profile_block(omega_exe)
    markers = _active_markers(content)
    if markers:
        begin, end = markers
        before, rest = content.split(begin, 1)
        _, after = rest.split(end, 1)
        return _trim_trailing_newlines(before) + ("\n" if before.strip() else "") + block + _ensure_leading_newline(after)
    return _trim_trailing_newlines(content) + ("\n\n" if content.strip() else "") + block + "\n"


def remove_omega_block(content: str) -> str:
    markers = _active_markers(content)
    if not markers:
        return content
    begin, end = markers
    before, rest = content.split(begin, 1)
    _, after = rest.split(end, 1)
    return _trim_trailing_newlines(before) + _ensure_leading_newline(after)


def global_command_status(project_root: Path | None = None) -> tuple[bool, str]:
    omega_exe = (project_root or Path(__file__).resolve().parents[1]) / ".venv" / "Scripts" / "omega.exe"
    path_match = _path_has_omega_exe(omega_exe)
    profile_match = _profile_has_omega_block(omega_exe)
    if profile_match:
        return True, "installed"
    if path_match:
        return True, "installed via PATH"
    return False, "not installed"


def _profile_has_omega_block(omega_exe: Path) -> bool:
    profile = _powershell_profile_path()
    if profile is None or not profile.exists():
        return False
    try:
        content = profile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return profile_contains_omega_block(content) and str(omega_exe) in content


def _path_has_omega_exe(omega_exe: Path) -> bool:
    discovered = shutil.which("omega")
    if not discovered:
        return False
    try:
        return Path(discovered).resolve() == omega_exe.resolve()
    except OSError:
        return False


def _powershell_profile_path() -> Path | None:
    documents = os.environ.get("USERPROFILE")
    if not documents:
        return None
    return Path(documents) / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"


def _trim_trailing_newlines(value: str) -> str:
    return value.rstrip("\r\n")


def _ensure_leading_newline(value: str) -> str:
    if not value:
        return "\n"
    return value if value.startswith(("\n", "\r\n")) else "\n" + value


def _active_markers(content: str) -> tuple[str, str] | None:
    if OMEGA_PROFILE_BEGIN in content and OMEGA_PROFILE_END in content:
        return OMEGA_PROFILE_BEGIN, OMEGA_PROFILE_END
    if LEGACY_PROFILE_BEGIN in content and LEGACY_PROFILE_END in content:
        return LEGACY_PROFILE_BEGIN, LEGACY_PROFILE_END
    return None
