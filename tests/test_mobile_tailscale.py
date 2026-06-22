from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from types import SimpleNamespace

from omega_agent.config import OmegaConfig
from omega_agent.config_store import default_config
from omega_agent.main import mobile_command
from omega_agent.mobile import tailscale as tailscale_module
from omega_agent.mobile.tailscale import omega_tailscale_serve_target, tailscale_serve, tailscale_status, tailscale_stop
from omega_agent.security.audit import run_security_audit


def cfg(tmp_path: Path, **overrides) -> OmegaConfig:
    values = {
        "model": "test",
        "workspace": tmp_path / "workspace",
        "require_approval": True,
        "db_path": tmp_path / "omega.db",
    }
    values.update(overrides)
    return OmegaConfig(**values)


def test_default_config_sets_mobile_tailscale():
    assert default_config()["mobile"]["mode"] == "tailscale"


def test_tailscale_status_reports_missing_cli(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tailscale_module.shutil, "which", lambda name: None)

    result = tailscale_status(cfg(tmp_path))

    assert result.ok is False
    assert result.installed is False
    assert "Installe Tailscale" in result.message


def test_tailscale_status_requires_connected_backend(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tailscale_module.shutil, "which", lambda name: "tailscale")

    def fake_run(command, **kwargs):
        if command[1:] == ["status", "--json"]:
            return SimpleNamespace(returncode=0, stdout='{"BackendState":"NeedsLogin"}', stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(tailscale_module.subprocess, "run", fake_run)

    result = tailscale_status(cfg(tmp_path))

    assert result.ok is False
    assert result.connected is False
    assert "connecte" in result.message.lower()


def test_tailscale_serve_uses_loopback_gateway_target(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path, host="0.0.0.0", port=8765)
    commands: list[list[str]] = []
    monkeypatch.setattr(tailscale_module.shutil, "which", lambda name: "tailscale")

    def fake_run(command, **kwargs):
        commands.append(command)
        args = command[1:]
        if args == ["status", "--json"]:
            return SimpleNamespace(returncode=0, stdout='{"BackendState":"Running","Self":{"Online":true,"DNSName":"omega.tailnet.ts.net."}}', stderr="")
        if args == ["serve", "status"]:
            return SimpleNamespace(returncode=0, stdout="Available within your tailnet:\nhttps://omega.tailnet.ts.net\n", stderr="")
        if args == ["serve", "status", "--json"]:
            return SimpleNamespace(returncode=0, stdout='{"url":"https://omega.tailnet.ts.net"}', stderr="")
        if args == ["serve", "http://127.0.0.1:8765"]:
            return SimpleNamespace(returncode=0, stdout="Available within your tailnet:\nhttps://omega.tailnet.ts.net\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(tailscale_module.subprocess, "run", fake_run)

    result = tailscale_serve(config)

    assert result.ok is True
    assert result.url == "https://omega.tailnet.ts.net"
    assert omega_tailscale_serve_target(config) == "http://127.0.0.1:8765"
    assert ["tailscale", "serve", "http://127.0.0.1:8765"] in commands
    assert not any(command[1] == "funnel" for command in commands)


def test_tailscale_stop_disables_only_omega_target(tmp_path: Path, monkeypatch):
    commands: list[list[str]] = []
    monkeypatch.setattr(tailscale_module.shutil, "which", lambda name: "tailscale")

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tailscale_module.subprocess, "run", fake_run)

    result = tailscale_stop(cfg(tmp_path))

    assert result.ok is True
    assert commands == [["tailscale", "serve", "http://127.0.0.1:8765", "off"]]


def test_tailscale_serve_timeout_returns_manual_instruction(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tailscale_module.shutil, "which", lambda name: "tailscale")

    def fake_run(command, **kwargs):
        args = command[1:]
        if args == ["status", "--json"]:
            return SimpleNamespace(returncode=0, stdout='{"BackendState":"Running","Self":{"Online":true}}', stderr="")
        if args == ["serve", "status"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args == ["serve", "http://127.0.0.1:8765"]:
            raise subprocess.TimeoutExpired(command, timeout=30, output="", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(tailscale_module.subprocess, "run", fake_run)

    result = tailscale_serve(cfg(tmp_path))

    assert result.ok is False
    assert "tailscale serve http://127.0.0.1:8765" in result.message


def test_mobile_command_prints_tailscale_status(tmp_path: Path, monkeypatch, capsys):
    target = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))
    data = default_config()
    data["workspace"]["path"] = str(tmp_path / "workspace")
    data["paths"]["db_path"] = str(tmp_path / "omega.db")
    target.write_text(__import__("json").dumps(data), encoding="utf-8")
    monkeypatch.setattr("omega_agent.main.tailscale_status", lambda config: SimpleNamespace(ok=True, message="Tailscale est connecte.", url="https://omega.tailnet.ts.net"))

    code = mobile_command(argparse.Namespace(mobile_command="tailscale", tailscale_command="status"))

    assert code == 0
    assert "Tailscale est connecte" in capsys.readouterr().out


def test_security_audit_tailscale_local_gateway_is_lower_risk_than_lan(tmp_path: Path):
    local_report = run_security_audit(cfg(tmp_path, host="127.0.0.1", mobile_mode="tailscale"))
    lan_report = run_security_audit(cfg(tmp_path, host="0.0.0.0", mobile_mode="tailscale"))

    assert any(finding.area == "mobile" and finding.severity == "info" for finding in local_report.findings)
    assert any(finding.area == "gateway" and finding.severity == "high" for finding in lan_report.findings)
