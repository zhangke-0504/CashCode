# -*- coding: utf-8 -*-
"""会话管理 REST API：列举、重命名、删除。"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ..memory.store import MemoryStore

router = APIRouter()

# 与 main.py 中 agent 共享同一个 MemoryStore 根目录。
# 此处使用独立实例（只读/写 metadata，不影响 agent 内存缓存）。
_store = MemoryStore(Path("memory"))


class RenameRequest(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title must not be empty")
        return v.strip()


@router.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    """返回所有会话列表，按最近活跃时间降序。"""
    sessions = _store.list_sessions()
    return {"sessions": sessions}


@router.patch("/sessions/{chat_id}")
async def rename_session(chat_id: str, body: RenameRequest) -> dict[str, Any]:
    """重命名指定会话。"""
    chat_dir = _store.base_dir / chat_id
    if not chat_dir.exists():
        raise HTTPException(status_code=404, detail="session not found")

    meta = _store.read_session_metadata(chat_id)
    meta["title"] = body.title
    _store.write_session_metadata(chat_id, meta)

    return {"chat_id": chat_id, "title": body.title}


@router.delete("/sessions/{chat_id}", status_code=204)
async def delete_session(chat_id: str) -> None:
    """删除指定会话及其全部数据。"""
    chat_dir = _store.base_dir / chat_id
    if not chat_dir.exists():
        raise HTTPException(status_code=404, detail="session not found")

    shutil.rmtree(chat_dir, ignore_errors=False)
