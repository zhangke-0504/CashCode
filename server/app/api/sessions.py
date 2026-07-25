# -*- coding: utf-8 -*-
"""会话管理 REST API：列举、重命名、删除。"""
from __future__ import annotations

import shutil
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ..memory.store import MemoryStore

router = APIRouter()

# 与 main.py 中 Agent 共享同一个 MemoryStore 根目录。
# 此处使用独立实例，只读写会话元数据，不影响 Agent 的内存缓存。
_SERVER_ROOT = Path(__file__).resolve().parents[2]
_store = MemoryStore(
    Path(os.environ.get("MEMORY_DIR", str(_SERVER_ROOT / "memory"))).resolve()
)


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


@router.get("/sessions/{chat_id}/messages")
async def get_session_messages(chat_id: str) -> dict[str, Any]:
    """返回会话中持久化的用户、助手消息及安全的能力选择收据。"""

    chat_dir = _store.base_dir / chat_id
    if not chat_dir.is_dir():
        raise HTTPException(status_code=404, detail="session not found")

    messages = _store.load_public_history(chat_id)
    return {"chat_id": chat_id, "messages": messages}


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
