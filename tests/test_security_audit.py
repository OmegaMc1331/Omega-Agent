import argparse
import json
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.main import security_command
from omega_agent.registries.plugins import PluginsRegistry
from omega_agent.security.audit import apply_safe_fixes, run_security_audit


def cfg(tmp_path: Path, **overrides) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    plugins = tmp_path / "plugins"
    values = {
        "model": "test",
        "workspace": workspace,
        "require_approval": True,
        "plugins_dir": plugins,
        "skills_dir": tmp_path / "skills",
        "db_path": tmp_path / "omega.db",
    }
    values.update(overrides)
    return OmegaConfig(**values)


def severities(report, area: str):
    return [finding.severity for finding in report.findings if finding.area == area]


def write_plugin(config: OmegaConfig, data: dict) -> None:
    plugin_dir = config.plugins_dir / data["id"]
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps(data), encoding="utf-8")


def test_gateway_0_0_0_0_is_high(tmp_path: Path):
    report = run_security_audit(cfg(tmp_path, host="0.0.0.0"))

    assert any(finding.area == "gateway" and finding.severity == "high" and "0.0.0.0" in finding.finding for finding in report.findings)


def test_untrusted_plugin_enabled_is_high(tmp_path: Path):
    config = cfg(tmp_path)
    write_plugin(
        config,
        {
            "id": "untrusted",
            "name": "Untrusted",
            "version": "0.1.0",
            "description": "Untrusted",
            "enabled": True,
            "trust_level": "untrusted",
            "permissions": ["skills.register"],
            "declares": {"tools": [], "skills": [], "channels": [], "hooks": []},
        },
    )

    report = run_security_audit(config)

    assert any(finding.area == "plugins" and finding.severity == "high" and "untrusted" in finding.finding for finding in report.findings)


def test_shell_without_approval_is_critical(tmp_path: Path):
    report = run_security_audit(cfg(tmp_path, require_approval=False))

    assert any(finding.area == "tools" and finding.severity == "critical" and "approval" in finding.finding.lower() for finding in report.findings)


def test_browser_user_profile_is_critical(tmp_path: Path):
    workspace = tmp_path / "workspace"
    report = run_security_audit(
        cfg(
            tmp_path,
            browser_enabled=True,
            browser_profile_dir=workspace / ".omega" / "Mozilla" / "Firefox" / "Profiles" / "default",
        )
    )

    assert any(finding.area == "browser" and finding.severity == "critical" for finding in report.findings)


def test_fix_safe_enables_approvals(tmp_path: Path):
    config = cfg(tmp_path, require_approval=False)
    env_path = tmp_path / ".env"

    fixed_config, fixed = apply_safe_fixes(config, env_path=env_path)

    assert fixed_config.require_approval is True
    assert any("Approval" in item for item in fixed)
    assert "OMEGA_REQUIRE_APPROVAL=true" in env_path.read_text(encoding="utf-8")


def test_json_output_is_valid(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("OMEGA_DB_PATH", str(tmp_path / "omega.db"))
    monkeypatch.setenv("OMEGA_PLUGINS_DIR", str(tmp_path / "plugins"))
    monkeypatch.setenv("OMEGA_SKILLS_DIR", str(tmp_path / "skills"))

    code = security_command(argparse.Namespace(security_command="audit", json_output=True, fix_safe=False))
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert code in {0, 1, 2}
    assert "score" in payload
    assert isinstance(payload["findings"], list)
