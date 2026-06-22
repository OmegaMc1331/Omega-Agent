from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.doctor import run_doctor, run_workspace_write_test
from omega_agent.runtime.approvals import ApprovalsStore
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.security.audit import run_security_audit
from omega_agent.tools.files import _append_file, _copy_file, _create_directory, _file_exists, _move_file, _write_file
from omega_agent.tools.shell import _run_shell


def test_doctor_reports_workspace_full_access_active(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, shell_full_access_in_workspace=True, allow_delete_in_workspace=True)
    monkeypatch.setattr("omega_agent.doctor.codex_version", lambda: "codex")
    monkeypatch.setattr("omega_agent.doctor.codex_login_status", lambda: (True, "logged in"))

    checks = {check.name: check.detail for check in run_doctor(cfg)}

    assert checks["Workspace full access"] == "active"
    assert checks["Codex sandbox mode"].endswith("effective=workspace-write")
    assert checks["Codex approval policy"] == "never"
    assert checks["Workspace write test"].startswith("PASS:")
    assert checks["Approval inside workspace"] == "disabled"
    assert checks["Outside workspace access"] == "denied"
    assert checks["Shell inside workspace"] == "enabled"
    assert checks["Delete inside workspace"] == "enabled"


def test_security_audit_full_access_is_not_critical_with_scoped_workspace(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, shell_full_access_in_workspace=True, allow_delete_in_workspace=True)

    report = run_security_audit(cfg)
    full_access_findings = [finding for finding in report.findings if "Workspace Full Access actif" in finding.finding]

    assert full_access_findings
    assert all(finding.severity != "critical" for finding in full_access_findings)


def test_tool_broker_does_not_create_approval_for_workspace_safe_write(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=True, workspace_full_access=True, db_path=tmp_path / "omega.db")
    sessions = SessionsStore(cfg)
    session = sessions.create_session("Full Access")
    sessions.set_agent_profile(session.id, "omega-coder")

    result = ToolBroker(cfg).call("write_file", {"relative_path": "note.txt", "content": "ok"}, session_id=session.id)

    assert result.status == "completed"
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "ok"
    assert ApprovalsStore(cfg).list(status="pending") == []


def test_config_json_full_access_values_are_read(tmp_path: Path, monkeypatch):
    from omega_agent.config_store import ensure_default_config, set_config_value

    config_path = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(config_path))
    ensure_default_config()
    set_config_value("workspace.path", str(tmp_path / "workspace"))
    set_config_value("workspace.full_access", True)
    set_config_value("workspace.require_approval", False)
    set_config_value("workspace.shell_full_access", True)
    set_config_value("workspace.allow_delete", True)
    set_config_value("workspace.allow_git_write", True)
    set_config_value("codex.sandbox_mode", "workspace-write")
    set_config_value("codex.approval_policy", "never")

    cfg = OmegaConfig.from_env()

    assert cfg.workspace == (tmp_path / "workspace").resolve()
    assert cfg.workspace_full_access is True
    assert cfg.require_approval is False
    assert cfg.shell_full_access_in_workspace is True
    assert cfg.allow_delete_in_workspace is True
    assert cfg.allow_git_write_in_workspace is True
    assert cfg.codex_sandbox_mode == "workspace-write"
    assert cfg.codex_approval_policy == "never"


def test_workspace_full_access_file_tools_modify_real_files(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, allow_delete_in_workspace=True)

    assert _write_file(cfg, "a.txt", "A") == "Fichier ecrit: a.txt"
    assert _append_file(cfg, "a.txt", "B") == "Fichier modifie: a.txt"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "AB"
    assert _create_directory(cfg, "dir") == "Dossier cree: dir"
    assert _copy_file(cfg, "a.txt", "dir/b.txt").startswith("Fichier copie")
    assert _move_file(cfg, "dir/b.txt", "dir/c.txt").startswith("Fichier deplace")
    assert _file_exists(cfg, "dir/c.txt") == "true"
    result = ToolBroker(cfg).call("delete_file", {"relative_path": "a.txt"})
    assert result.status == "completed"
    assert not (tmp_path / "a.txt").exists()


def test_workspace_full_access_shell_and_denials(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, shell_full_access_in_workspace=True, allow_delete_in_workspace=True)

    output = _run_shell(cfg, "cmd /c dir" if __import__("sys").platform == "win32" else "ls")

    assert output
    assert _run_shell(cfg, "sudo ls").startswith("Commande refusee:")
    assert _run_shell(cfg, "rm -rf /").startswith("Commande refusee:")


def test_tool_broker_full_access_integration_no_approval_and_denies_outside(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    cfg = OmegaConfig(model="test", workspace=workspace, require_approval=True, workspace_full_access=True, shell_full_access_in_workspace=True, allow_delete_in_workspace=True, db_path=tmp_path / "omega.db")
    session = SessionsStore(cfg).create_session("Integration")
    broker = ToolBroker(cfg)

    write = broker.call("write_file", {"relative_path": "test.txt", "content": "hello"}, session_id=session.id)
    append = broker.call("append_file", {"path": "test.txt", "content": " world"}, session_id=session.id)
    shell = broker.call("run_shell", {"command": "cmd /c dir" if __import__("sys").platform == "win32" else "ls"}, session_id=session.id)
    delete = broker.call("delete_file", {"relative_path": "test.txt"}, session_id=session.id)
    denied = broker.call("write_file", {"relative_path": str(outside), "content": "x"}, session_id=session.id)

    assert write.status == append.status == shell.status == delete.status == "completed"
    assert not (workspace / "test.txt").exists()
    assert denied.status == "denied"
    assert not outside.exists()
    assert ApprovalsStore(cfg).list(status="pending") == []


def test_workspace_doctor_performs_real_write_test(tmp_path: Path):
    workspace = tmp_path / "workspace"
    cfg = OmegaConfig(
        model="test",
        workspace=workspace,
        require_approval=False,
        workspace_full_access=True,
    )

    check = run_workspace_write_test(cfg)

    assert check.ok is True
    assert check.detail.startswith("PASS:")
    assert not (workspace / ".omega-write-test").exists()


def test_workspace_doctor_reports_codex_sandbox_workspace_write(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(
        model="test",
        workspace=tmp_path,
        require_approval=False,
        workspace_full_access=True,
        codex_sandbox_mode="read-only",
    )
    monkeypatch.setattr("omega_agent.doctor.codex_version", lambda: "codex")
    monkeypatch.setattr("omega_agent.doctor.codex_login_status", lambda: (True, "logged in"))

    checks = {check.name: check for check in run_doctor(cfg)}

    assert checks["Codex sandbox mode"].ok is True
    assert checks["Codex sandbox mode"].detail.endswith("effective=workspace-write")


def test_outside_workspace_still_denied(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    cfg = OmegaConfig(
        model="test",
        workspace=workspace,
        require_approval=False,
        workspace_full_access=True,
        codex_sandbox_mode="workspace-write",
        codex_approval_policy="never",
    )

    result = ToolBroker(cfg).call("write_file", {"relative_path": str(outside), "content": "blocked"})

    assert result.status == "denied"
    assert not outside.exists()
