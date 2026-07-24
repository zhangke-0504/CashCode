from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..skills.evolution import EvolutionService
from ..skills.models import SkillConflictError, SkillError, SkillPermissionError

router = APIRouter(prefix="/skill-evolution/proposals", tags=["skill-evolution"])


def _service(request: Request) -> EvolutionService:
    value = getattr(request.app.state, "skill_evolution", None)
    if value is None:
        raise HTTPException(status_code=503, detail="Skill evolution service is unavailable")
    return value


def _raise(exc: Exception) -> None:
    if isinstance(exc, SkillPermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, SkillConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, SkillError):
        raise HTTPException(status_code=404 if "not found" in str(exc) else 422, detail=str(exc)) from exc
    raise exc


@router.get("")
async def list_proposals(request: Request) -> dict[str, Any]:
    service = _service(request)
    return {"enabled": service.config.enabled, "items": service.list_proposals()}


@router.get("/{proposal_id}")
async def get_proposal(request: Request, proposal_id: str) -> dict[str, Any]:
    proposal = _service(request).get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    return proposal


@router.post("/{proposal_id}/reject")
async def reject_proposal(request: Request, proposal_id: str) -> dict[str, Any]:
    try:
        return _service(request).reject(proposal_id)
    except Exception as exc:
        _raise(exc)


@router.post("/{proposal_id}/approve")
async def approve_proposal(request: Request, proposal_id: str) -> dict[str, Any]:
    try:
        return _service(request).approve(proposal_id)
    except Exception as exc:
        _raise(exc)
