from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.doctor import run_doctor
from omega_agent.runtime.approvals import ApprovalsStore
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.security.audit import run_security_audit


def test_doctor_reports_workspace_full_access_active(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, shell_full_access_in_workspace=True, allow_delete_in_workspace=True)
    monkeypatch.setattr("omega_agent.doctor.codex_version", lambda: "codex")
    monkeypatch.setattr("omega_agent.doctor.codex_login_status", lambda: (True, "logged in"))

    checks = {check.name: check.detail for check in run_doctor(cfg)}

    assert checks["Workspace full access"] == "active"
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
