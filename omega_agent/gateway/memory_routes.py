from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from omega_agent.runtime.decision_log import DecisionLog
from omega_agent.runtime.memory_compaction import compact_project_memory
from omega_agent.runtime.project_memory import (
    MEMORY_SCOPES,
    MEMORY_STATUSES,
    MEMORY_TYPES,
    ProjectMemoryStore,
    default_project_memory_provenance,
)


def register_memory_routes(router: APIRouter) -> None:
    @router.get("/api/memory")
    async def api_memory(
        request: Request,
        q: str = "",
        scope: str | None = None,
        project_id: str | None = None,
        status: str = "active",
        limit: int = Query(100, ge=1, le=500),
    ):
        store = _memory_store(request)
        if scope is not None and scope not in MEMORY_SCOPES:
            raise HTTPException(status_code=400, detail="Scope memoire invalide.")
        try:
            if q.strip():
                return [memory.as_api() for memory in store.search_memory(q, scope=scope, project_id=project_id, limit=limit)]
            return [memory.as_api() for memory in store.list_memories(scope=scope, project_id=project_id, status=status, limit=limit)]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/memory")
    async def api_create_memory(payload: dict, request: Request):
        store = _memory_store(request)
        content = str(payload.get("content") or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="Memoire vide.")
        try:
            memory = store.create_memory(
                scope=str(payload.get("scope") or "global"),
                scope_id=_optional_str(payload.get("scope_id")),
                project_id=_optional_str(payload.get("project_id")),
                session_id=_optional_str(payload.get("session_id")),
                run_id=_optional_str(payload.get("run_id")),
                key=str(payload.get("key") or ""),
                content=content,
                type=str(payload.get("type") or "fact"),
                provenance=payload.get("provenance") or default_project_memory_provenance("Omega Control"),
                tags=_string_list(payload.get("tags")),
                confidence=float(payload.get("confidence", 0.8)),
                importance=int(payload.get("importance", 3)),
                created_by=str(payload.get("created_by") or "user"),
                summary=_optional_str(payload.get("summary")),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return memory.as_api()

    @router.get("/api/memory/search")
    async def api_search_memory(
        request: Request,
        q: str = Query("", min_length=0, max_length=500),
        scope: str | None = None,
        project_id: str | None = None,
        limit: int = Query(10, ge=1, le=100),
    ):
        store = _memory_store(request)
        return [memory.as_api() for memory in store.search_memory(q, scope=scope, project_id=project_id, limit=limit)]

    @router.get("/api/memory/suggestions")
    async def api_memory_suggestions(request: Request, status: str = "pending", project_id: str | None = None):
        try:
            return [suggestion.as_api() for suggestion in _memory_store(request).list_suggestions(status=status, project_id=project_id)]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/memory/suggestions/{suggestion_id}/accept")
    async def api_accept_memory_suggestion(suggestion_id: str, request: Request):
        try:
            memory = _memory_store(request).accept_suggestion(suggestion_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if memory is None:
            raise HTTPException(status_code=404, detail="Suggestion memoire introuvable.")
        return memory.as_api()

    @router.post("/api/memory/suggestions/{suggestion_id}/reject")
    async def api_reject_memory_suggestion(suggestion_id: str, request: Request):
        if not _memory_store(request).reject_suggestion(suggestion_id):
            raise HTTPException(status_code=404, detail="Suggestion memoire introuvable.")
        return {"ok": True}

    @router.get("/api/memory/{memory_id}")
    async def api_get_memory(memory_id: str, request: Request):
        memory = _memory_store(request).get_memory(memory_id)
        if memory is None:
            raise HTTPException(status_code=404, detail="Memoire introuvable.")
        data = memory.as_api()
        data["provenance_entries"] = [item.as_api() for item in _memory_store(request).list_provenance(memory_id)]
        return data

    @router.patch("/api/memory/{memory_id}")
    async def api_patch_memory(memory_id: str, payload: dict, request: Request):
        try:
            memory = _memory_store(request).update_memory(
                memory_id,
                content=payload.get("content") if "content" in payload else None,
                tags=_string_list(payload.get("tags")) if "tags" in payload else None,
                status=payload.get("status") if "status" in payload else None,
                confidence=payload.get("confidence") if "confidence" in payload else None,
                importance=payload.get("importance") if "importance" in payload else None,
                summary=payload.get("summary") if "summary" in payload else None,
                key=payload.get("key") if "key" in payload else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if memory is None:
            raise HTTPException(status_code=404, detail="Memoire introuvable.")
        return memory.as_api()

    @router.delete("/api/memory/{memory_id}")
    async def api_delete_memory(memory_id: str, request: Request):
        if not _memory_store(request).delete_memory(memory_id):
            raise HTTPException(status_code=404, detail="Memoire introuvable.")
        return {"ok": True}

    @router.get("/api/decisions")
    async def api_decisions(request: Request, project_id: str | None = None, status: str | None = None):
        try:
            return [decision.as_api() for decision in _decision_log(request).list_decisions(project_id=project_id, status=status)]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/api/decisions")
    async def api_create_decision(payload: dict, request: Request):
        try:
            decision = _decision_log(request).add_decision(
                title=str(payload.get("title") or ""),
                content=str(payload.get("content") or ""),
                reason=str(payload.get("reason") or ""),
                project_id=_optional_str(payload.get("project_id")),
                session_id=_optional_str(payload.get("session_id")),
                run_id=_optional_str(payload.get("run_id")),
                provenance=payload.get("provenance") or default_project_memory_provenance("Omega Control"),
                alternatives=_string_list(payload.get("alternatives")),
                created_by=str(payload.get("created_by") or "user"),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return decision.as_api()

    @router.patch("/api/decisions/{decision_id}")
    async def api_patch_decision(decision_id: str, payload: dict, request: Request):
        try:
            decision = _decision_log(request).patch_decision(decision_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if decision is None:
            raise HTTPException(status_code=404, detail="Decision introuvable.")
        return decision.as_api()

    @router.delete("/api/decisions/{decision_id}")
    async def api_delete_decision(decision_id: str, request: Request):
        decision = _decision_log(request).archive_decision(decision_id)
        if decision is None:
            raise HTTPException(status_code=404, detail="Decision introuvable.")
        return {"ok": True}

    @router.get("/api/projects/{project_id}/knowledge")
    async def api_project_knowledge(project_id: str, request: Request):
        memory_store = _memory_store(request)
        memories = memory_store.list_memories(project_id=project_id, status="active", limit=100)
        decisions = _decision_log(request).list_decisions(project_id=project_id, status="active", limit=100)
        return {
            "project_id": project_id,
            "important_memories": [memory.as_api() for memory in memories if memory.importance >= 4][:20],
            "procedures": [memory.as_api() for memory in memories if memory.type == "procedure"][:20],
            "warnings": [memory.as_api() for memory in memories if memory.type == "warning"][:20],
            "resolved_errors": [memory.as_api() for memory in memories if "resolved" in memory.tags or "erreur" in memory.tags or "error" in memory.tags][:20],
            "decisions": [decision.as_api() for decision in decisions],
            "conflicts": [conflict.as_api() for conflict in memory_store.list_conflicts(project_id=project_id)],
        }

    @router.get("/api/projects/{project_id}/decisions")
    async def api_project_decisions(project_id: str, request: Request):
        return [decision.as_api() for decision in _decision_log(request).list_decisions(project_id=project_id)]

    @router.post("/api/projects/{project_id}/compact-memory")
    async def api_compact_project_memory(project_id: str, request: Request):
        return compact_project_memory(request.app.state.gateway_state.config, project_id)


def _memory_store(request: Request) -> ProjectMemoryStore:
    return ProjectMemoryStore(request.app.state.gateway_state.config)


def _decision_log(request: Request) -> DecisionLog:
    return DecisionLog(request.app.state.gateway_state.config)


def _string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _optional_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
