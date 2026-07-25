from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field

from ..skills.loader import MAX_SKILL_ZIP_BYTES, read_skill_package
from ..skills.models import (
    SkillConflictError,
    SkillError,
    SkillPermissionError,
    SkillSource,
)
from ..skills.store import SkillStore

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillCreateRequest(BaseModel):
    name: str
    content: str
    source: SkillSource = SkillSource.USER
    support_files: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class SkillReplaceRequest(BaseModel):
    content: str
    support_files: dict[str, str] | None = None
    expected_hash: str | None = None


class SkillEnabledRequest(BaseModel):
    enabled: bool


def _store(request: Request) -> SkillStore:
    value = getattr(request.app.state, "skill_store", None)
    if value is None:
        raise HTTPException(status_code=503, detail="Skill service is unavailable")
    return value


def _raise_skill_error(exc: Exception) -> None:
    if isinstance(exc, SkillPermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, SkillConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, SkillError):
        code = 404 if "not found" in str(exc).lower() else 422
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    raise exc


@router.get("")
async def list_skills(
    request: Request,
    source: str | None = None,
    enabled: bool | None = None,
    availability: str | None = None,
    query: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    catalog = _store(request).catalog
    if query:
        catalog_size = max(1, len(catalog.list()))
        records = [
            record
            for _, record in catalog.search(
                query, catalog_size, include_disabled=True
            )
        ]
        if source:
            records = [record for record in records if record.source.value == source]
        if enabled is not None:
            records = [record for record in records if record.enabled is enabled]
        if availability:
            records = [record for record in records if record.availability.value == availability]
    else:
        records = catalog.list(source=source, enabled=enabled, availability=availability)
    total = len(records)
    start = (page - 1) * page_size
    return {
        "items": [record.to_dict() for record in records[start:start + page_size]],
        "total": total,
        "page": page,
        "page_size": page_size,
        "invalid": catalog.invalid,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_skill(request: Request, body: SkillCreateRequest) -> dict[str, Any]:
    try:
        return _store(request).create(
            body.name,
            body.content,
            source=body.source,
            support_files=body.support_files,
            enabled=body.enabled,
        )
    except Exception as exc:
        _raise_skill_error(exc)


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_skill(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    """接收并安装单个 ZIP 格式的用户 Skill。"""

    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail="Skill package must be a .zip file")
    data = await file.read(MAX_SKILL_ZIP_BYTES + 1)
    if len(data) > MAX_SKILL_ZIP_BYTES:
        raise HTTPException(status_code=422, detail="Skill ZIP is too large")
    try:
        return _store(request).import_zip(data)
    except Exception as exc:
        _raise_skill_error(exc)


@router.get("/{name}")
async def get_skill(request: Request, name: str) -> dict[str, Any]:
    record = _store(request).catalog.get(name)
    if record is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    data = record.to_dict(include_path=True)
    try:
        _, body = _store(request).catalog.load_body(name)
        data["body_preview"] = body[:4000]
        data["body_truncated"] = len(body) > 4000
    except SkillError as exc:
        data["validation_errors"] = [str(exc)]
    data["versions"] = _store(request).versions(name)
    return data


@router.get("/{name}/content")
async def get_skill_content(request: Request, name: str) -> dict[str, Any]:
    """返回编辑器需要的完整 SKILL.md，不暴露宿主机路径。"""

    try:
        return _store(request).read_content(name)
    except Exception as exc:
        _raise_skill_error(exc)


@router.post("/{name}/validate")
async def validate_skill(request: Request, name: str) -> dict[str, Any]:
    record = _store(request).catalog.get(name)
    if record is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    try:
        manifest, _, digest, _ = read_skill_package(record.path)
    except SkillError as exc:
        return {"valid": False, "errors": [str(exc)]}
    return {"valid": True, "name": manifest.name, "hash": digest, "errors": []}


@router.put("/{name}")
async def replace_skill(request: Request, name: str, body: SkillReplaceRequest) -> dict[str, Any]:
    try:
        return _store(request).replace(
            name,
            body.content,
            support_files=body.support_files,
            expected_hash=body.expected_hash,
        )
    except Exception as exc:
        _raise_skill_error(exc)


@router.patch("/{name}/enabled")
async def set_skill_enabled(request: Request, name: str, body: SkillEnabledRequest) -> dict[str, Any]:
    try:
        return _store(request).set_enabled(name, body.enabled)
    except Exception as exc:
        _raise_skill_error(exc)


@router.delete("/{name}", status_code=204)
async def delete_skill(request: Request, name: str) -> None:
    try:
        _store(request).delete(name)
    except Exception as exc:
        _raise_skill_error(exc)


@router.delete("/invalid/{source}/{directory}")
async def delete_invalid_skill(
    request: Request, source: str, directory: str
) -> dict[str, str]:
    """删除用户确认的无效 Skill 包，并保留可恢复快照。"""

    try:
        return _store(request).delete_invalid(source, directory)
    except Exception as exc:
        _raise_skill_error(exc)


@router.get("/{name}/versions")
async def list_skill_versions(request: Request, name: str) -> dict[str, Any]:
    if _store(request).catalog.get(name) is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"name": name, "versions": _store(request).versions(name)}


@router.post("/{name}/rollback/{version}")
async def rollback_skill(request: Request, name: str, version: str) -> dict[str, Any]:
    try:
        return _store(request).rollback(name, version)
    except Exception as exc:
        _raise_skill_error(exc)
