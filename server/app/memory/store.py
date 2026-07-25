"""MemoryStore：对话历史的文件持久化层。

这是 spore ``core.agent.memory.MemoryStore`` 的精简版本（Step 1），
只保留 history.jsonl 读写和 cursor 游标机制，不包含 MEMORY.md、SOUL.md
以及 Consolidator / Dream 等高层功能。

目录结构：
    <base_dir>/
    └── <chat_id>/
        ├── history.jsonl   # 追加式对话历史，每行一条 JSON 记录
        └── .cursor         # 最新 cursor 值（整数文本），加速 _next_cursor
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..selections import safe_persisted_selections

logger = logging.getLogger(__name__)


class MemoryStore:
    """纯文件 I/O 层：读写 history.jsonl 和 cursor 文件。

    每个 chat_id 对应一个子目录，彼此独立，不存在并发写冲突。
    文件写入使用同步 I/O（pathlib / open），足够轻量，不引入 aiofiles。
    """

    def __init__(self, base_dir: Path) -> None:
        """
        参数：
            base_dir: 所有 chat_id 子目录的根目录，例如 Path("memory")。
                      目录本身在首次写入时按需创建，此处不预建。
        """
        self.base_dir = base_dir

    # ------------------------------------------------------------------
    # 路径辅助
    # ------------------------------------------------------------------

    def _chat_dir(self, chat_id: str) -> Path:
        """返回 chat_id 对应的子目录，首次调用时自动创建。"""
        d = self.base_dir / chat_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _history_file(self, chat_id: str) -> Path:
        return self._chat_dir(chat_id) / "history.jsonl"

    def _cursor_file(self, chat_id: str) -> Path:
        return self._chat_dir(chat_id) / ".cursor"

    # ------------------------------------------------------------------
    # 游标管理
    # ------------------------------------------------------------------

    def _next_cursor(self, chat_id: str) -> int:
        """读取 .cursor 文件并返回下一个 cursor 值（自增 1）。

        文件不存在或内容无效时回落到读取 history.jsonl 最后一行；
        两者都为空则从 1 开始。
        """
        cf = self._cursor_file(chat_id)
        if cf.exists():
            try:
                return int(cf.read_text(encoding="utf-8").strip()) + 1
            except (ValueError, OSError):
                pass
        # 回落：读 history.jsonl 最后一行
        last = self._read_last_entry(chat_id)
        if last and isinstance(last.get("cursor"), int):
            return last["cursor"] + 1
        return 1

    def _write_cursor(self, chat_id: str, cursor: int) -> None:
        self._cursor_file(chat_id).write_text(str(cursor), encoding="utf-8")

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def append_turn(
        self,
        chat_id: str,
        user_content: str,
        assistant_content: str,
        user_metadata: dict[str, Any] | None = None,
    ) -> None:
        """将一轮对话（user + assistant）追加到 history.jsonl。

        两条记录写入同一次 open，cursor 连续递增，最后同步更新 .cursor 文件。
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        user_cursor = self._next_cursor(chat_id)
        assistant_cursor = user_cursor + 1

        user_record = {
            "cursor": user_cursor,
            "timestamp": ts,
            "role": "user",
            "content": user_content,
            **safe_persisted_selections(user_metadata or {}),
        }
        assistant_record = {
            "cursor": assistant_cursor,
            "timestamp": ts,
            "role": "assistant",
            "content": assistant_content,
        }

        history_file = self._history_file(chat_id)
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(user_record, ensure_ascii=False) + "\n")
            f.write(json.dumps(assistant_record, ensure_ascii=False) + "\n")

        self._write_cursor(chat_id, assistant_cursor)
        logger.debug(
            "MemoryStore: appended turn for chat_id=%s (cursors %d-%d)",
            chat_id, user_cursor, assistant_cursor,
        )

    def append_summary(
        self,
        chat_id: str,
        summary: str,
        keep_from_cursor: int | None = None,
    ) -> None:
        """将 Consolidator 生成的摘要追加到 history.jsonl。

        写入 ``role: "summary"`` 类型的单条记录，cursor 自增。
        keep_from_cursor 若提供，写入记录的 keep_from_cursor 字段，
        供 load_history_smart 正确恢复 to_keep 消息。
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        cursor = self._next_cursor(chat_id)
        record: dict[str, Any] = {
            "cursor": cursor,
            "timestamp": ts,
            "role": "summary",
            "content": summary,
        }
        if keep_from_cursor is not None:
            record["keep_from_cursor"] = keep_from_cursor
        history_file = self._history_file(chat_id)
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._write_cursor(chat_id, cursor)
        logger.debug(
            "MemoryStore: appended summary for chat_id=%s (cursor %d, keep_from_cursor=%s)",
            chat_id, cursor, keep_from_cursor,
        )

    def append_tool_turn(
        self,
        chat_id: str,
        user_content: str,
        tool_calls_msg: dict[str, Any],
        tool_results: list[dict[str, Any]],
        final_reply: str,
    ) -> None:
        """将含工具调用的完整轮次原子写入 history.jsonl。

        依次写入：user → tool_calls → tool_result(s) → assistant，cursor 连续自增。
        所有记录在一次 open("a") 调用中写入，任何异常均不写入（原子性保证）。

        参数：
            tool_calls_msg: Runner 返回的 assistant 消息，含 tool_calls 字段
            tool_results: list of {"tool_call_id": ..., "content": ...} 结果消息
            final_reply: LLM 最终文字回复
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        # 预先计算用户、工具调用、工具结果和助手消息所需的全部游标值。
        n_records = 3 + len(tool_results)  # 固定三条消息，加上每一条工具结果。
        first_cursor = self._next_cursor(chat_id)
        cursors = list(range(first_cursor, first_cursor + n_records))

        # 构建所有记录
        records: list[dict[str, Any]] = []

        # 用户消息。
        records.append({
            "cursor": cursors[0], "timestamp": ts, "role": "user", "content": user_content,
        })
        # 助手发起工具调用的消息。
        tool_calls_record: dict[str, Any] = {
            "cursor": cursors[1],
            "timestamp": ts,
            "role": "tool_calls",
            "content": _tool_calls_summary(tool_calls_msg),
            "tool_calls": tool_calls_msg.get("tool_calls", []),
        }
        records.append(tool_calls_record)
        # 一条或多条工具结果。
        for i, tr in enumerate(tool_results):
            records.append({
                "cursor": cursors[2 + i],
                "timestamp": ts,
                "role": "tool",
                "content": tr.get("content", ""),
                "tool_call_id": tr.get("tool_call_id", ""),
            })
        # 助手最终回复。
        records.append({
            "cursor": cursors[-1], "timestamp": ts, "role": "assistant", "content": final_reply,
        })

        # 原子写入
        history_file = self._history_file(chat_id)
        lines = [json.dumps(r, ensure_ascii=False) + "\n" for r in records]
        try:
            with open(history_file, "a", encoding="utf-8") as f:
                f.writelines(lines)
        except OSError:
            logger.exception(
                "MemoryStore: failed to write tool turn for chat_id=%s; no records written",
                chat_id,
            )
            return

        self._write_cursor(chat_id, cursors[-1])
        logger.debug(
            "MemoryStore: appended tool turn for chat_id=%s (cursors %d-%d, %d tool_results)",
            chat_id, cursors[0], cursors[-1], len(tool_results),
        )

    def append_traced_turn(
        self,
        chat_id: str,
        user_content: str,
        durable_messages: list[dict[str, Any]],
        final_reply: str,
        user_metadata: dict[str, Any] | None = None,
    ) -> None:
        """持久化一个完整工具调用 Turn 中的所有耐久消息。"""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        payloads: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": user_content,
                **safe_persisted_selections(user_metadata or {}),
            }
        ]
        for message in durable_messages:
            role = message.get("role")
            if role == "assistant" and message.get("tool_calls"):
                payloads.append({
                    "role": "tool_calls",
                    "content": _tool_calls_summary(message),
                    "tool_calls": message.get("tool_calls", []),
                })
            elif role == "assistant" and message.get("content"):
                payloads.append({
                    "role": "assistant",
                    "content": message.get("content", ""),
                })
            elif role == "tool":
                payloads.append({
                    "role": "tool",
                    "content": message.get("content", ""),
                    "tool_call_id": message.get("tool_call_id", ""),
                    "name": message.get("name", ""),
                })
        payloads.append({"role": "assistant", "content": final_reply})

        first_cursor = self._next_cursor(chat_id)
        records = []
        for offset, payload in enumerate(payloads):
            records.append({
                "cursor": first_cursor + offset,
                "timestamp": ts,
                **payload,
            })
        history_file = self._history_file(chat_id)
        with open(history_file, "a", encoding="utf-8") as handle:
            handle.writelines(
                json.dumps(record, ensure_ascii=False) + "\n" for record in records
            )
        self._write_cursor(chat_id, records[-1]["cursor"])

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def load_history(self, chat_id: str) -> list[dict[str, Any]]:
        """从 history.jsonl 读取全量历史，返回 OpenAI messages 格式列表。

        返回值形如 [{"role": "user", "content": "..."}, ...]，
        可直接传入 openai.chat.completions.create(messages=...)。
        文件不存在时返回空列表（新会话）。
        """
        history_file = self.base_dir / chat_id / "history.jsonl"
        if not history_file.exists():
            return []

        messages: list[dict[str, Any]] = []
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning(
                            "MemoryStore: skipping malformed line in %s", history_file
                        )
                        continue
                    role = entry.get("role")
                    content = entry.get("content", "")
                    if role in ("user", "assistant") and content:
                        messages.append({"role": role, "content": content})
                    elif role == "summary" and content:
                        # 摘要记录映射为助手消息，加前缀让模型知晓这是压缩内容。
                        messages.append({"role": "assistant", "content": f"[历史摘要] {content}"})
                    # 未知角色静默跳过，保持向前兼容。
        except OSError:
            logger.exception("MemoryStore: failed to read %s", history_file)
            return []

        logger.debug(
            "MemoryStore: loaded %d messages for chat_id=%s", len(messages), chat_id
        )
        return messages

    def load_public_history(self, chat_id: str) -> list[dict[str, Any]]:
        """返回用户和助手消息，并附带仅用于展示的安全选择收据。"""

        messages: list[dict[str, Any]] = []
        for entry in self._read_raw_entries(chat_id):
            role = entry.get("role")
            if role not in ("user", "assistant"):
                continue
            content = entry.get("content", "")
            if not isinstance(content, str):
                content = str(content or "")
            item: dict[str, Any] = {"role": role, "content": content}
            if role == "user":
                item.update(safe_persisted_selections(entry))
            messages.append(item)
        return messages

    def read_unprocessed_history(
        self,
        chat_id: str,
        since_cursor: int,
    ) -> list[dict[str, Any]]:
        """返回 cursor 值大于 since_cursor 的所有历史条目。

        供 Step 2 Consolidator / Step 3 Dream 增量处理使用；
        当前 Step 1 中不被 AgentLoop 主流程调用。
        """
        history_file = self.base_dir / chat_id / "history.jsonl"
        if not history_file.exists():
            return []

        entries: list[dict[str, Any]] = []
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("cursor", 0) > since_cursor:
                        entries.append(entry)
        except OSError:
            logger.exception("MemoryStore: failed to read %s", history_file)

        return entries

    def _read_raw_entries(self, chat_id: str) -> list[dict[str, Any]]:
        """读取 history.jsonl 全量原始条目，不做 role 映射，直接返回 JSON 对象列表。"""
        history_file = self.base_dir / chat_id / "history.jsonl"
        if not history_file.exists():
            return []
        entries: list[dict[str, Any]] = []
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            logger.exception("MemoryStore: failed to read %s", history_file)
        return entries

    def load_history_smart(
        self, chat_id: str
    ) -> tuple[list[dict[str, Any]], int]:
        """智能加载：基于 keep_from_cursor 元数据正确恢复待保留消息。

        加载策略（按优先级）：
        1. 找到最后一条 summary，读取其 keep_from_cursor 字段
        2. 若存在 keep_from_cursor：加载该 summary + 所有 cursor >= keep_from_cursor 的非 summary 条目
        3. 若无 keep_from_cursor（旧格式兜底）：加载该 summary + cursor > summary_cursor 的条目
        4. 若无 summary：全量加载

        修复了旧实现"从 summary 文件位置往后读"的 Bug：to_keep 消息在文件中的
        cursor < summary cursor（因先于 summary 写入），旧逻辑会丢弃它们。
        """
        raw = self._read_raw_entries(chat_id)
        if not raw:
            return [], 0

        # 找到最后一条摘要及其元数据。
        last_summary_entry: dict[str, Any] | None = None
        for e in raw:
            if e.get("role") == "summary":
                last_summary_entry = e

        if last_summary_entry is None:
            # 没有摘要时全量加载，此时尚未发生上下文压缩。
            messages: list[dict[str, Any]] = []
            for e in raw:
                if e.get("role") == "summary":
                    content = e.get("content", "")
                    if content:
                        messages.append({"role": "assistant", "content": f"[历史摘要] {content}"})
                    continue
                msg = _entry_to_message(e)
                if msg:
                    messages.append(msg)
            logger.debug(
                "MemoryStore: smart-loaded %d messages for chat_id=%s (no summary, last_consolidated=0)",
                len(messages), chat_id,
            )
            return messages, 0

        summary_cursor = last_summary_entry.get("cursor", 0)
        keep_from_cursor = last_summary_entry.get("keep_from_cursor")  # 新格式元数据

        messages = []
        # 先加载摘要作为前缀。
        summary_content = last_summary_entry.get("content", "")
        if summary_content:
            messages.append({"role": "assistant", "content": f"[历史摘要] {summary_content}"})

        # 加载压缩后需要保留的消息。
        for e in raw:
            role = e.get("role")
            if role == "summary":
                continue  # 跳过所有摘要，包括已单独加载的最后一条。
            content = e.get("content", "")
            cursor = e.get("cursor", 0)

            if keep_from_cursor is not None:
                # 新格式：keep_from_cursor 精确标记保留边界。
                if cursor >= keep_from_cursor:
                    msg = _entry_to_message(e)
                    if msg:
                        messages.append(msg)
            else:
                # 旧格式兜底：只加载摘要之后写入的条目。
                if cursor > summary_cursor:
                    msg = _entry_to_message(e)
                    if msg:
                        messages.append(msg)

        logger.debug(
            "MemoryStore: smart-loaded %d messages for chat_id=%s "
            "(summary_cursor=%d, keep_from_cursor=%s, last_consolidated=1)",
            len(messages), chat_id, summary_cursor, keep_from_cursor,
        )
        return messages, 1

    def get_keep_from_cursor(self, chat_id: str, to_keep_count: int) -> int | None:
        """返回 history.jsonl 中第一条待保留消息的 cursor。

        从文件末尾读取指定数量的非摘要记录；记录不足或缺少 cursor 时返回 None。
        Consolidator 使用该值把 keep_from_cursor 写入摘要记录。
        """
        if to_keep_count <= 0:
            return None
        raw = self._read_raw_entries(chat_id)
        non_summary = [e for e in raw if e.get("role") != "summary"]
        if len(non_summary) < to_keep_count:
            return None
        first_keep = non_summary[-to_keep_count]
        cursor = first_keep.get("cursor")
        return int(cursor) if cursor is not None else None

    # ------------------------------------------------------------------
    # 全局记忆（MEMORY.md）与 Dream 游标
    # ------------------------------------------------------------------

    def read_memory(self) -> str:
        """读取全局 MEMORY.md，文件不存在时返回空字符串。"""
        memory_file = self.base_dir / "MEMORY.md"
        try:
            return memory_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def write_memory(self, content: str) -> None:
        """覆写全局 MEMORY.md（不存在时自动创建）。"""
        memory_file = self.base_dir / "MEMORY.md"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        memory_file.write_text(content, encoding="utf-8")
        logger.debug("MemoryStore: wrote MEMORY.md (%d chars)", len(content))

    def read_soul(self) -> str:
        """读取 SOUL.md（Agent 人格文件），文件不存在时返回空字符串。"""
        soul_file = self.base_dir / "SOUL.md"
        try:
            return soul_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def write_soul(self, content: str) -> None:
        """覆写 SOUL.md（不存在时自动创建）。"""
        soul_file = self.base_dir / "SOUL.md"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        soul_file.write_text(content, encoding="utf-8")
        logger.debug("MemoryStore: wrote SOUL.md (%d chars)", len(content))

    def get_dream_cursors(self) -> dict[str, int]:
        """读取全局 dream cursor 映射（JSON），不存在时返回空字典。

        格式：{"<chat_id>": <last_processed_cursor>, ...}
        """
        cursor_file = self.base_dir / ".dream_cursor"
        if not cursor_file.exists():
            return {}
        try:
            return json.loads(cursor_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("MemoryStore: failed to read .dream_cursor, resetting")
            return {}

    def set_dream_cursors(self, cursors: dict[str, int]) -> None:
        """将 dream cursor 映射写入 .dream_cursor（JSON 格式，原子覆写）。"""
        cursor_file = self.base_dir / ".dream_cursor"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        cursor_file.write_text(json.dumps(cursors, ensure_ascii=False), encoding="utf-8")

    def list_chat_ids(self) -> list[str]:
        """返回 base_dir 下所有非隐藏子目录名称（即所有 chat_id）。"""
        if not self.base_dir.exists():
            return []
        return [
            d.name
            for d in self.base_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]

    def list_sessions(self) -> list[dict[str, Any]]:
        """扫描 base_dir，返回所有会话的摘要信息列表，按 updated_at 降序排序。

        每个元素：{"chat_id": str, "title": str, "updated_at": str}
        - title：取自 session_metadata.json 的 title 字段，缺失时为"新对话"
        - updated_at：history.jsonl 的 mtime，文件不存在时用目录 mtime
        """
        if not self.base_dir.exists():
            return []

        sessions: list[dict[str, Any]] = []
        for d in self.base_dir.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            chat_id = d.name

            # 读取会话元数据。
            meta = self.read_session_metadata(chat_id)
            title: str = meta.get("title") or "新对话"

            # 更新时间优先采用 history.jsonl 的文件修改时间。
            history_file = d / "history.jsonl"
            if history_file.exists():
                mtime = history_file.stat().st_mtime
            else:
                mtime = d.stat().st_mtime

            import time as _time
            updated_at = _time.strftime("%Y-%m-%dT%H:%M:%S", _time.localtime(mtime))

            sessions.append({
                "chat_id": chat_id,
                "title": title,
                "updated_at": updated_at,
            })

        sessions.sort(key=lambda s: s["updated_at"], reverse=True)
        return sessions

    # ------------------------------------------------------------------
    # 会话元数据（V2 新增：供 ActivatedToolSet 等跨轮次状态存储使用）
    # ------------------------------------------------------------------

    def _metadata_file(self, chat_id: str) -> Path:
        return self._chat_dir(chat_id) / "metadata.json"

    def read_session_metadata(self, chat_id: str) -> dict[str, Any]:
        """读取 chat_id 对应的 session metadata。文件不存在时返回空 dict。"""
        path = self._metadata_file(chat_id)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to read session metadata for %s, returning empty", chat_id)
            return {}

    def write_session_metadata(self, chat_id: str, data: dict[str, Any]) -> None:
        """原子写入 chat_id 对应的 session metadata。"""
        import os
        import uuid as _uuid
        path = self._metadata_file(chat_id)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{_uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _read_last_entry(self, chat_id: str) -> dict[str, Any] | None:
        """从 history.jsonl 末尾高效读取最后一行并解析。"""
        history_file = self.base_dir / chat_id / "history.jsonl"
        try:
            with open(history_file, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return None
                read_size = min(size, 4096)
                f.seek(size - read_size)
                data = f.read().decode("utf-8", errors="replace")
                lines = [ln for ln in data.split("\n") if ln.strip()]
                if not lines:
                    return None
                return json.loads(lines[-1])
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None


# ---------------------------------------------------------------------------
# 模块级辅助函数，供 MemoryStore 方法和测试复用
# ---------------------------------------------------------------------------

def _entry_to_message(entry: dict[str, Any]) -> dict[str, Any] | None:
    """把 history.jsonl 原始记录转换为 OpenAI messages 格式。

    对摘要或未知角色等应跳过的记录返回 None；支持 user、assistant、
    tool_calls 和 tool 四种角色。
    """
    role = entry.get("role")
    content = entry.get("content", "")

    if role == "user" and content:
        return {"role": "user", "content": content}

    if role == "assistant" and content:
        return {"role": "assistant", "content": content}

    if role == "tool_calls":
        # 恢复发起工具调用的助手消息。
        tool_calls = entry.get("tool_calls")
        if tool_calls:
            return {
                "role": "assistant",
                "content": content or "",
                "tool_calls": tool_calls,
            }
        return None

    if role == "tool":
        tool_call_id = entry.get("tool_call_id", "")
        if tool_call_id and content:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": entry.get("name", ""),
                "content": content,
            }
        return None

    # 跳过摘要和未知角色等记录。
    return None


def _tool_calls_summary(tool_calls_msg: dict[str, Any]) -> str:
    """为 content 字段生成便于阅读的工具调用摘要。"""
    calls = tool_calls_msg.get("tool_calls") or []
    names = [c.get("function", {}).get("name", "?") for c in calls if isinstance(c, dict)]
    return f"[TOOL_CALLS: {', '.join(names)}]" if names else "[TOOL_CALLS]"
