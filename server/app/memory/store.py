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

logger = logging.getLogger(__name__)


class MemoryStore:
    """纯文件 I/O 层：读写 history.jsonl 和 cursor 文件。

    每个 chat_id 对应一个子目录，彼此独立，不存在并发写冲突。
    文件写入使用同步 I/O（pathlib / open），足够轻量，不引入 aiofiles。
    """

    def __init__(self, base_dir: Path) -> None:
        """
        Args:
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
    # cursor 管理
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
        # 预先计算所有 cursor 值（user + tool_calls + N tool_results + assistant）
        n_records = 3 + len(tool_results)  # user + tool_calls + results + assistant
        first_cursor = self._next_cursor(chat_id)
        cursors = list(range(first_cursor, first_cursor + n_records))

        # 构建所有记录
        records: list[dict[str, Any]] = []

        # user
        records.append({
            "cursor": cursors[0], "timestamp": ts, "role": "user", "content": user_content,
        })
        # tool_calls（assistant 发起工具调用的消息）
        tool_calls_record: dict[str, Any] = {
            "cursor": cursors[1],
            "timestamp": ts,
            "role": "tool_calls",
            "content": _tool_calls_summary(tool_calls_msg),
            "tool_calls": tool_calls_msg.get("tool_calls", []),
        }
        records.append(tool_calls_record)
        # tool_result(s)
        for i, tr in enumerate(tool_results):
            records.append({
                "cursor": cursors[2 + i],
                "timestamp": ts,
                "role": "tool",
                "content": tr.get("content", ""),
                "tool_call_id": tr.get("tool_call_id", ""),
            })
        # assistant 最终回复
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
                        # 摘要记录映射为 assistant 消息，加前缀让 LLM 知晓这是压缩内容。
                        messages.append({"role": "assistant", "content": f"[历史摘要] {content}"})
                    # 未知 role 静默跳过，保持向前兼容
        except OSError:
            logger.exception("MemoryStore: failed to read %s", history_file)
            return []

        logger.debug(
            "MemoryStore: loaded %d messages for chat_id=%s", len(messages), chat_id
        )
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
        """Smart Load：基于 keep_from_cursor 元数据正确恢复 to_keep 消息。

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

        # 找到最后一条 summary 及其元数据
        last_summary_entry: dict[str, Any] | None = None
        for e in raw:
            if e.get("role") == "summary":
                last_summary_entry = e

        if last_summary_entry is None:
            # 无 summary：全量加载，nothing is consolidated
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
        # 先加载 summary 作为前缀
        summary_content = last_summary_entry.get("content", "")
        if summary_content:
            messages.append({"role": "assistant", "content": f"[历史摘要] {summary_content}"})

        # 加载 to_keep 消息
        for e in raw:
            role = e.get("role")
            if role == "summary":
                continue  # 跳过所有 summary（包括已单独加载的最后一条）
            content = e.get("content", "")
            cursor = e.get("cursor", 0)

            if keep_from_cursor is not None:
                # 新格式：keep_from_cursor 精确标记保留边界
                if cursor >= keep_from_cursor:
                    msg = _entry_to_message(e)
                    if msg:
                        messages.append(msg)
            else:
                # 旧格式兜底：只加载 summary 之后写入的条目
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
        """Return the cursor of the first to_keep message in history.jsonl.

        Reads the last `to_keep_count` non-summary entries from the file.
        Returns None if the file doesn't have enough entries or cursor is missing.
        Used by the Consolidator to record keep_from_cursor in the summary record.
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
    # 全局记忆（MEMORY.md）与 Dream cursor
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
# Module-level helpers (used by MemoryStore methods and tests)
# ---------------------------------------------------------------------------

def _entry_to_message(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a raw history.jsonl entry to an OpenAI messages-format dict.

    Returns None for entries that should be skipped (e.g. summary, unknown role).
    Handles: user, assistant, tool_calls, tool.
    """
    role = entry.get("role")
    content = entry.get("content", "")

    if role == "user" and content:
        return {"role": "user", "content": content}

    if role == "assistant" and content:
        return {"role": "assistant", "content": content}

    if role == "tool_calls":
        # Restore assistant message that triggered tool calls
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
                "content": content,
            }
        return None

    # summary, unknown, etc. → skip
    return None


def _tool_calls_summary(tool_calls_msg: dict[str, Any]) -> str:
    """Extract a human-readable summary of tool calls for the 'content' field."""
    calls = tool_calls_msg.get("tool_calls") or []
    names = [c.get("function", {}).get("name", "?") for c in calls if isinstance(c, dict)]
    return f"[TOOL_CALLS: {', '.join(names)}]" if names else "[TOOL_CALLS]"
