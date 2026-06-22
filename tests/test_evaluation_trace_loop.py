import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.evals.eval_runner import EvalRunner
from omega_agent.evals.failure_clustering import FailureClustering
from omega_agent.evals.metrics import MetricsStore
from omega_agent.evals.run_scoring import RunScoring
from omega_agent.evals.trace_collector import TraceCollector
from omega_agent.gateway.server import create_app
from omega_agent.runtime.durable_runtime import DurableRuntime
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.storage.migrations import migrate


def cfg(tmp_path: Path) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return OmegaConfig(
        model="test",
        workspace=workspace,
        require_approval=False,
        workspace_full_access=True,
        shell_full_access_in_workspace=True,
        allow_delete_in_workspace=True,
        allow_git_write_in_workspace=True,
        db_path=tmp_path / "omega.db",
        evals_default_dataset_dir=tmp_path / "evals",
        evals_report_dir=tmp_path / "reports",
    )


def test_eval_migrations_create_tables(tmp_path: Path):
    config = cfg(tmp_path)
    migrate(config)
    migrate(config)

    with connect_runtime_db(config) as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}

    assert {"eval_runs", "eval_cases", "task_outcomes", "run_metrics", "failure_clusters"}.issubset(tables)


def test_run_metrics_created_after_run_and_score(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Eval metrics")

    result = ToolBroker(config).call("write_file", {"relative_path": "metric.txt", "content": "OK"}, session_id=session.id)

    assert result.status == "completed"
    run = DurableRuntime(config).list_runs(session_id=session.id, limit=1)[0]
    metrics = MetricsStore(config).get_run_metrics(run.id)
    score = RunScoring(config).score_run(run.id)

    assert metrics is not None
    assert metrics["tool_calls_count"] == 1
    assert metrics["files_changed_count"] == 1
    assert score["score"] >= 80


def test_trace_export_is_redacted(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Trace")
    runtime = DurableRuntime(config)
    run = runtime.create_run(session.id, "secret sk-12345678901234567890")
    runtime.start_run(run.id)
    runtime.fail_run(run.id, "Authorization: Bearer abcdefghijklmnop")

    exported = TraceCollector(config).export_trace_json(run.id)

    assert "sk-123456" not in exported
    assert "abcdefghijklmnop" not in exported
    assert "[REDACTED]" in exported


def test_eval_dataset_file_created_and_expected_denied(tmp_path: Path):
    config = cfg(tmp_path)
    dataset = tmp_path / "dataset.json"
    outside = tmp_path / "outside.txt"
    dataset.write_text(
        json.dumps(
            {
                "name": "acceptance",
                "cases": [
                    {
                        "name": "create file",
                        "prompt": "Crée eval-created.txt dans mon workspace avec le texte OK",
                        "expected_files_created": ["eval-created.txt"],
                        "expected_contains": {"eval-created.txt": "OK"},
                        "expected_tool_calls": ["write_file"],
                    },
                    {
                        "name": "deny outside",
                        "prompt": f"Crée {outside} avec le texte NO",
                        "expected_denied": True,
                        "expected_tool_calls": ["write_file"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run_async(EvalRunner(config).run_eval_dataset(str(dataset)))

    assert result["status"] == "succeeded"
    assert result["summary"]["passed"] == 2
    assert (config.workspace / "eval-created.txt").read_text(encoding="utf-8") == "OK"
    assert not outside.exists()


def test_failure_clustering_groups_denied_actions(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Cluster")
    outside = tmp_path / "outside.txt"

    ToolBroker(config).call("write_file", {"relative_path": str(outside), "content": "x"}, session_id=session.id)
    clusters = FailureClustering(config).cluster_recent_failures()

    assert clusters
    assert any(cluster["count"] >= 1 for cluster in clusters)


def test_eval_and_trace_endpoints(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("API")
    ToolBroker(config).call("write_file", {"relative_path": "api.txt", "content": "OK"}, session_id=session.id)
    run = DurableRuntime(config).list_runs(session_id=session.id, limit=1)[0]
    app = create_app(config)
    client = TestClient(app)

    assert client.get("/api/evals/metrics").status_code == 200
    assert client.get("/api/traces").status_code == 200
    trace = client.get(f"/api/traces/{run.id}")
    score = client.post(f"/api/runs/{run.id}/score")
    outcome = client.patch(f"/api/runs/{run.id}/outcome", json={"outcome": "success"})

    assert trace.status_code == 200
    assert score.status_code == 200
    assert outcome.status_code == 200
    assert outcome.json()["outcome"] == "success"


def test_eval_cli_metrics_and_traces(tmp_path: Path):
    config_path = tmp_path / "config.json"
    db_path = tmp_path / "omega.db"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "OMEGA_CONFIG_PATH": str(config_path),
            "OMEGA_DB_PATH": str(db_path),
            "OMEGA_WORKSPACE": str(workspace),
        }
    )

    metrics = subprocess.run([sys.executable, "-m", "omega_agent.main", "evals", "metrics"], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, check=False, timeout=60)
    traces = subprocess.run([sys.executable, "-m", "omega_agent.main", "traces", "list"], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, check=False, timeout=60)

    assert metrics.returncode == 0, metrics.stdout + metrics.stderr
    assert traces.returncode == 0, traces.stdout + traces.stderr
    assert "aggregate" in metrics.stdout


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)
