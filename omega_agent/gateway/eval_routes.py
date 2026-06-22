from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from omega_agent.evals.eval_reports import EvalReports
from omega_agent.evals.eval_runner import EvalRunner
from omega_agent.evals.failure_clustering import FailureClustering
from omega_agent.evals.metrics import MetricsStore
from omega_agent.evals.run_scoring import RunScoring
from omega_agent.evals.task_outcomes import TaskOutcomesStore
from omega_agent.evals.trace_collector import TraceCollector


def register_eval_routes(router: APIRouter) -> None:
    @router.get("/api/evals")
    async def api_evals(request: Request, limit: int = Query(100, ge=1, le=500)):
        _ensure_enabled(request)
        return EvalRunner(_config(request)).list_eval_runs(limit=limit)

    @router.post("/api/evals/run")
    async def api_run_eval(payload: dict, request: Request):
        _ensure_enabled(request)
        dataset = str(payload.get("dataset") or payload.get("dataset_name") or "").strip()
        if not dataset:
            raise HTTPException(status_code=400, detail="Dataset requis.")
        try:
            return await EvalRunner(_config(request)).run_eval_dataset(dataset)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/evals/reports")
    async def api_eval_reports(request: Request):
        _ensure_enabled(request)
        return EvalReports(_config(request)).list_reports()

    @router.get("/api/evals/metrics")
    async def api_eval_metrics(request: Request, project_id: str | None = None, days: int = Query(7, ge=1, le=365)):
        _ensure_enabled(request)
        metrics = MetricsStore(_config(request))
        return {
            "aggregate": metrics.aggregate_metrics(project_id=project_id, days=days),
            "models": metrics.model_performance_summary(),
            "tools": metrics.tool_reliability_summary(),
            "agents": metrics.agent_profile_performance_summary(),
            "policy": metrics.policy_friction_summary(),
        }

    @router.get("/api/evals/failures")
    async def api_eval_failures(request: Request):
        _ensure_enabled(request)
        return FailureClustering(_config(request)).cluster_recent_failures()

    @router.patch("/api/evals/failures/{cluster_id}")
    async def api_patch_failure(cluster_id: str, payload: dict, request: Request):
        _ensure_enabled(request)
        status = str(payload.get("status") or "").strip()
        try:
            if status:
                return FailureClustering(_config(request)).mark_cluster_fixed(cluster_id, status=status)
            return FailureClustering(_config(request)).suggest_cluster_fix(cluster_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/evals/{eval_run_id}")
    async def api_get_eval(eval_run_id: str, request: Request):
        _ensure_enabled(request)
        try:
            return EvalRunner(_config(request)).get_eval_run(eval_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/evals/{eval_run_id}/cases")
    async def api_eval_cases(eval_run_id: str, request: Request):
        _ensure_enabled(request)
        return EvalRunner(_config(request)).list_cases(eval_run_id)

    @router.post("/api/evals/{eval_run_id}/cancel")
    async def api_cancel_eval(eval_run_id: str, request: Request):
        _ensure_enabled(request)
        try:
            return EvalRunner(_config(request)).cancel_eval_run(eval_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/traces")
    async def api_traces(request: Request, limit: int = Query(100, ge=1, le=500), status: str | None = None):
        _ensure_enabled(request)
        return TraceCollector(_config(request)).list_traces(limit=limit, status=status)

    @router.get("/api/traces/{run_id}")
    async def api_trace(run_id: str, request: Request):
        _ensure_enabled(request)
        try:
            return TraceCollector(_config(request)).collect_run_trace(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/traces/{run_id}/export")
    async def api_trace_export(run_id: str, request: Request):
        _ensure_enabled(request)
        try:
            return TraceCollector(_config(request)).collect_run_trace(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/runs/{run_id}/score")
    async def api_score_run(run_id: str, request: Request):
        _ensure_enabled(request)
        try:
            return RunScoring(_config(request)).score_run(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.patch("/api/runs/{run_id}/outcome")
    async def api_update_run_outcome(run_id: str, payload: dict, request: Request):
        _ensure_enabled(request)
        outcome = str(payload.get("outcome") or "").strip()
        try:
            return TaskOutcomesStore(_config(request)).update_outcome(
                run_id,
                outcome,
                user_feedback=payload.get("user_feedback"),
                human_score=payload.get("human_score"),
                reason=payload.get("reason"),
            ).as_api()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


def _config(request: Request):
    return request.app.state.gateway_state.config


def _ensure_enabled(request: Request) -> None:
    if not _config(request).evals_enabled:
        raise HTTPException(status_code=403, detail="Evaluation Loop desactive par configuration.")
