from __future__ import annotations

import pytest

from omega_agent.main import main


def test_update_command_exists(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc_info:
        main(["update", "--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--force" in output
    assert "--branch" in output
    assert "--skip-frontend" in output
    assert "--skip-doctor" in output

