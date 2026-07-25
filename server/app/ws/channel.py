"""CashCode 的 WebSocket 通道，是 spore ``core.channels.websocket`` 的最简版本。

这里沿用 spore 的线上协议，使同一套前端代码可以连接两种后端。

客户端 → 服务端信封（带有 ``type`` 字段的 JSON）：
  {"type": "message", "chat_id": "...", "content": "...", "metadata": {"revert_keep_user_turns": 1}}
  {"type": "ping"}
  {"type": "new_chat"}
  {"type": "attach",  "chat_id": "..."}
  {"type": "cancel",  "chat_id": "..."}

服务端 → 客户端帧：
  {"event": "ready",      "chat_id": "...", "client_id": "..."}   — 建立连接时
  {"event": "attached",   "chat_id": "..."}                       — new_chat / attach 后
  {"event": "session_updated", "chat_id": "...", "title": "...", "updated_at": "..."}
  {"event": "delta",      "chat_id": "...", "text": "...",  "stream_id": ...}
  {"event": "stream_end", "chat_id": "...", "stream_id": ...}
  {"event": "done",       "chat_id": "...", "duration_sec": 1.23}
  {"event": "error",      "detail": "..."}
  {"event": "pong"}
  {"event": "message",    "chat_id": "...", "text": "..."}        — 非流式兜底消息
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from ..bus.events import InboundMessage, OutboundMessage
from ..bus.queue import MessageBus
from ..selections import SelectionValidationError, sanitize_selection_metadata

logger = logging.getLogger(__name__)

# 会话标识必须简短且安全，可以是 UUID 或带作用域的键。
_CHAT_ID_RE = re.compile(r"^[A-Za-z0-9_:-]{1,64}$")


def _is_valid_chat_id(value: Any) -> bool:
    return isinstance(value, str) and _CHAT_ID_RE.match(value) is not None


def _parse_envelope(raw: str) -> dict[str, Any] | None:
    """仅当帧是含字符串 ``type`` 的 JSON 时，返回带类型的信封字典。"""
    text = raw.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("type"), str):
        return None
    return data


class WebSocketChannel:
    """运行独立的 WebSocket 服务器，并在它与 MessageBus 之间转发消息。

    不包含身份认证、静态文件和会话持久化，只保留 spore 中最核心的
    连接、订阅与扇出机制。
    """

    def __init__(self, bus: MessageBus, *, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.bus = bus
        self.host = host
        self.port = port

        # 会话标识映射到订阅该会话的连接集合。
        self._subs: dict[str, set[Any]] = {}
        # 连接映射到其订阅的会话标识集合，便于断开时快速清理。
        self._conn_chats: dict[Any, set[str]] = {}

        self._stop_event: asyncio.Event | None = None
        self._server_task: asyncio.Task | None = None
        self._dispatch_task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # 订阅关系维护
    # ------------------------------------------------------------------

    def _attach(self, conn: Any, chat_id: str) -> None:
        """以幂等方式让 *conn* 订阅 *chat_id*。"""
        self._subs.setdefault(chat_id, set()).add(conn)
        self._conn_chats.setdefault(conn, set()).add(chat_id)

    def _cleanup_conn(self, conn: Any) -> None:
        """从所有订阅集合中移除 *conn*。"""
        for cid in self._conn_chats.pop(conn, set()):
            bucket = self._subs.get(cid)
            if bucket:
                bucket.discard(conn)
                if not bucket:
                    self._subs.pop(cid, None)

    # ------------------------------------------------------------------
    # 底层发送辅助方法
    # ------------------------------------------------------------------

    async def _send(self, conn: Any, payload: dict[str, Any]) -> None:
        try:
            await conn.send(json.dumps(payload, ensure_ascii=False))
        except ConnectionClosed:
            self._cleanup_conn(conn)
        except Exception as exc:
            logger.warning("ws: send failed: %s", exc)

    async def _fan_out(self, chat_id: str, payload: dict[str, Any]) -> None:
        """将 *payload* 发送给 *chat_id* 的所有订阅者。"""
        conns = list(self._subs.get(chat_id, ()))
        if not conns:
            logger.warning("ws: no subscribers for chat_id=%s", chat_id)
            return
        for conn in conns:
            await self._send(conn, payload)

    # ------------------------------------------------------------------
    # 连接生命周期
    # ------------------------------------------------------------------

    async def _connection_loop(self, conn: ServerConnection) -> None:
        client_id = f"client-{uuid.uuid4().hex[:12]}"
        default_chat_id = str(uuid.uuid4())

        self._attach(conn, default_chat_id)
        await self._send(conn, {
            "event": "ready",
            "chat_id": default_chat_id,
            "client_id": client_id,
        })
        logger.info("ws: client connected client_id=%s chat_id=%s", client_id, default_chat_id)

        try:
            async for raw in conn:
                if isinstance(raw, bytes):
                    try:
                        raw = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                await self._ingest_frame(conn, client_id, raw)
        except ConnectionClosed:
            pass
        except Exception as exc:
            logger.debug("ws: connection ended with error: %s", exc)
        finally:
            self._cleanup_conn(conn)
            logger.info("ws: client disconnected client_id=%s", client_id)

    async def _ingest_frame(self, conn: Any, client_id: str, raw: str) -> None:
        envelope = _parse_envelope(raw)
        if envelope is None:
            await self._send(conn, {"event": "error", "detail": "typed JSON envelope required"})
            return
        await self._dispatch_envelope(conn, client_id, envelope)

    # ------------------------------------------------------------------
    # 信封分发
    # ------------------------------------------------------------------

    async def _dispatch_envelope(
        self, conn: Any, client_id: str, envelope: dict[str, Any]
    ) -> None:
        t = envelope.get("type")

        if t == "ping":
            await self._send(conn, {"event": "pong"})
            return

        if t == "new_chat":
            new_id = str(uuid.uuid4())
            self._attach(conn, new_id)
            await self._send(conn, {"event": "attached", "chat_id": new_id})
            return

        if t == "attach":
            cid = envelope.get("chat_id")
            if not _is_valid_chat_id(cid):
                await self._send(conn, {"event": "error", "detail": "invalid chat_id"})
                return
            self._attach(conn, cid)
            await self._send(conn, {"event": "attached", "chat_id": cid})
            return

        if t in ("cancel", "stop"):
            cid = envelope.get("chat_id")
            if not _is_valid_chat_id(cid):
                await self._send(conn, {"event": "error", "detail": "invalid chat_id"})
                return
            # 发布停止信号，使 Agent 可以取消仍在执行的对话轮次。
            await self.bus.publish_inbound(InboundMessage(
                channel="websocket",
                sender_id=client_id,
                chat_id=str(cid),
                content="/stop",
            ))
            await self._send(conn, {"event": "stop_ack", "chat_id": cid})
            return

        if t == "message":
            cid = envelope.get("chat_id")
            content = envelope.get("content")
            if not _is_valid_chat_id(cid):
                await self._send(conn, {"event": "error", "detail": "invalid chat_id"})
                return
            if not isinstance(content, str) or not content.strip():
                await self._send(conn, {
                    "event": "error",
                    "detail": "missing content",
                    "chat_id": cid,
                })
                return
            # 选择元数据来自客户端，必须在进入消息总线前完成结构和数量校验。
            try:
                metadata = sanitize_selection_metadata(
                    envelope.get("metadata"), require_llm=True
                )
            except SelectionValidationError as exc:
                await self._send(conn, {
                    "event": "error",
                    "detail": str(exc),
                    "chat_id": cid,
                })
                return
            # 自动订阅，使客户端可以省略单独的附加会话帧。
            self._attach(conn, cid)
            await self.bus.publish_inbound(InboundMessage(
                channel="websocket",
                sender_id=client_id,
                chat_id=str(cid),
                content=content,
                metadata=metadata,
            ))
            return

        await self._send(conn, {"event": "error", "detail": f"unknown type: {t!r}"})

    # ------------------------------------------------------------------
    # 出站分发器（消息总线 → WebSocket）
    # ------------------------------------------------------------------

    async def _dispatch_outbound(self) -> None:
        """把消息总线中的 OutboundMessage 转发给 WebSocket 订阅者。"""
        logger.info("ws: outbound dispatcher started")
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(
                        self.bus.consume_outbound(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                await self._route_outbound(msg)
        except asyncio.CancelledError:
            pass
        logger.info("ws: outbound dispatcher stopped")

    async def _route_outbound(self, msg: OutboundMessage) -> None:
        """将 OutboundMessage 转换为对应的线上协议帧。"""
        meta = msg.metadata or {}
        chat_id = msg.chat_id

        if meta.get("_session_updated"):
            await self._fan_out(chat_id, {
                "event": "session_updated",
                "chat_id": chat_id,
                "title": str(meta.get("_title", "")),
                "updated_at": str(meta.get("_updated_at", "")),
            })
            return

        if meta.get("_user_error"):
            await self._fan_out(chat_id, {
                "event": "error",
                "detail": msg.content,
                "chat_id": chat_id,
            })
            return

        if meta.get("_turn_done"):
            await self._fan_out(chat_id, {
                "event": "done",
                "chat_id": chat_id,
                "duration_sec": float(meta.get("_duration_sec", 0.0) or 0.0),
            })
            return

        if meta.get("_stream_delta"):
            if meta.get("_stream_end"):
                await self._fan_out(chat_id, {
                    "event": "stream_end",
                    "chat_id": chat_id,
                    "stream_id": meta.get("_stream_id"),
                })
            else:
                await self._fan_out(chat_id, {
                    "event": "delta",
                    "chat_id": chat_id,
                    "text": msg.content,
                    "stream_id": meta.get("_stream_id"),
                })
            return

        if meta.get("_tool_call"):
            await self._fan_out(chat_id, {
                "event": "tool_call",
                "chat_id": chat_id,
                "tool_name": meta.get("_tool_name", ""),
                "stream_id": meta.get("_stream_id"),
            })
            return

        if meta.get("_tool_result"):
            await self._fan_out(chat_id, {
                "event": "tool_result",
                "chat_id": chat_id,
                "tool_name": meta.get("_tool_name", ""),
                "result": meta.get("_result", ""),
                "stream_id": meta.get("_stream_id"),
            })
            return

        # 通用消息帧（非流式兜底）。
        await self._fan_out(chat_id, {
            "event": "message",
            "chat_id": chat_id,
            "text": msg.content,
        })

    # ------------------------------------------------------------------
    # 启动与停止
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动 WebSocket 服务器和出站分发器。"""
        self._running = True
        self._stop_event = asyncio.Event()
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())

        async def handler(conn: ServerConnection) -> None:
            await self._connection_loop(conn)

        logger.info("ws: server listening on ws://%s:%d/", self.host, self.port)

        async def runner() -> None:
            async with serve(
                handler,
                self.host,
                self.port,
                ping_interval=20,
                ping_timeout=20,
                reuse_address=True,
            ):
                assert self._stop_event is not None
                await self._stop_event.wait()

        self._server_task = asyncio.create_task(runner())
        await self._server_task

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        if self._dispatch_task and not self._dispatch_task.done():
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
        self._subs.clear()
        self._conn_chats.clear()
