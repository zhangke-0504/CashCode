"""SimpleDream：定时两阶段 LLM 处理器，从对话历史提炼长期记忆写入 MEMORY.md。

这是 spore ``core.agent.memory.Dream`` 的精简版本（Step 3），
去掉了 AgentRunner/文件工具、git auto-commit、per-line age annotation 等复杂依赖，
改用两次普通 LLM 调用（Phase 1 分析 + Phase 2 生成）更新全局 MEMORY.md。

数据流：
  所有 chat_id 的 history.jsonl（未处理部分）
      │ Phase 1
      ▼
  分析报告（应新增/更新/删除哪些事实）
      │ Phase 2
      ▼
  新的完整 MEMORY.md 内容 → 写入文件
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ..llm.errors import is_expected_provider_failure
from ..llm.models import LLMNotConfiguredError
from ..llm.runtime import LLMRuntime, LLMSnapshot
from ..logging_config import log_event, safe_exception_info
from .store import MemoryStore

logger = logging.getLogger(__name__)


class SimpleDream:
    """两阶段 LLM 记忆处理器。

    Phase 1：分析新增 history 条目，生成变更报告。
    Phase 2：基于报告和当前 MEMORY.md，输出完整的新 MEMORY.md。
    """

    MAX_BATCH: int = 50  # 每次最多处理的 history 条目数
    OPERATION_TIMEOUT: float = 120.0

    def __init__(
        self,
        runtime: LLMRuntime,
        store: MemoryStore,
        *,
        operation_timeout: float = OPERATION_TIMEOUT,
    ) -> None:
        if operation_timeout <= 0:
            raise ValueError("operation_timeout must be positive")
        self._runtime = runtime
        self._store = store
        self._operation_timeout = operation_timeout

    @staticmethod
    def _log_phase_failure(phase: str, exc: Exception) -> None:
        if is_expected_provider_failure(exc):
            logger.warning("Dream: %s provider request failed (%s)", phase, type(exc).__name__)
        else:
            logger.warning(
                "Dream: %s failed", phase, exc_info=safe_exception_info(exc)
            )

    # ------------------------------------------------------------------
    # 数据收集
    # ------------------------------------------------------------------

    def _collect_new_entries(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """收集所有 chat_id 中未处理的 history 条目。

        返回 (entries, updated_cursors)：
          - entries: 汇总后按 timestamp 排序的新条目列表（上限 MAX_BATCH）
          - updated_cursors: 各 chat_id 对应的最新 cursor（用于后续更新 dream cursor）
        """
        dream_cursors = self._store.get_dream_cursors()
        chat_ids = self._store.list_chat_ids()

        all_entries: list[dict[str, Any]] = []
        updated_cursors: dict[str, int] = dict(dream_cursors)

        for chat_id in chat_ids:
            since = dream_cursors.get(chat_id, 0)
            new_entries = self._store.read_unprocessed_history(chat_id, since_cursor=since)
            for entry in new_entries:
                # 附上来源 chat_id，便于调试
                entry_with_source = dict(entry)
                entry_with_source["_chat_id"] = chat_id
                all_entries.append(entry_with_source)
            if new_entries:
                updated_cursors[chat_id] = new_entries[-1]["cursor"]

        # 按 timestamp 排序，截取批次上限
        all_entries.sort(key=lambda e: e.get("timestamp", ""))
        batch = all_entries[: self.MAX_BATCH]

        return batch, updated_cursors

    @staticmethod
    def _format_entries(entries: list[dict[str, Any]]) -> str:
        """格式化 history 条目为 LLM 可读文本。"""
        lines = []
        for e in entries:
            ts = e.get("timestamp", "?")
            role = e.get("role", "unknown").upper()
            content = e.get("content", "").strip()
            if content:
                lines.append(f"[{ts}] {role}: {content}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LLM 调用
    # ------------------------------------------------------------------

    async def _phase1_analyze(
        self,
        snapshot: LLMSnapshot,
        entries_text: str,
        current_memory: str,
    ) -> str:
        """Phase 1：分析新对话历史，产出变更报告。"""
        system_prompt = (
            "你是一个记忆分析助手。你的任务是分析用户的最新对话历史，"
            "结合当前的长期记忆文件，判断哪些信息值得长期记住。\n\n"
            "请输出一份简洁的分析报告，包含：\n"
            "1. 应新增到长期记忆的事实（用户基本信息、偏好、正在进行的项目等）\n"
            "2. 应更新的已有条目（如果有变化）\n"
            "3. 应删除的过时条目（如果有）\n\n"
            "只关注有长期价值的信息，忽略临时性闲聊内容。"
        )
        user_content = (
            f"## 最新对话历史\n{entries_text}\n\n"
            f"## 当前长期记忆\n{current_memory or '（尚无记忆）'}"
        )
        response = await snapshot.client.chat.completions.create(
            model=snapshot.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=False,
        )
        return response.choices[0].message.content or ""

    async def _phase2_update(
        self,
        snapshot: LLMSnapshot,
        analysis: str,
        current_memory: str,
    ) -> str:
        """Phase 2：基于分析报告，生成完整的新 MEMORY.md 内容。"""
        system_prompt = (
            "你是一个记忆文件编辑助手。你的任务是根据分析报告，"
            "更新长期记忆文件（MEMORY.md）。\n\n"
            "规则：\n"
            "- 保留已有记忆中仍然有效的条目\n"
            "- 按分析报告新增、更新或删除相应条目\n"
            "- 使用清晰的 Markdown 格式，按类别组织（如：用户信息、项目、偏好等）\n"
            "- 只输出 MEMORY.md 的内容，不要包含任何解释或前言\n"
            "- 如果没有任何值得记录的信息，输出空字符串"
        )
        user_content = (
            f"## 分析报告\n{analysis}\n\n"
            f"## 当前 MEMORY.md\n{current_memory or '（尚无记忆）'}"
        )
        response = await snapshot.client.chat.completions.create(
            model=snapshot.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            stream=False,
        )
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def run(self) -> bool:
        """执行一次 Dream 处理。返回 True 表示有实际工作完成。

        流程：
          1. 收集所有 chat_id 的未处理 history 条目
          2. 若无新条目，直接返回 False
          3. Phase 1：LLM 分析 → 变更报告
          4. Phase 2：LLM 生成 → 新 MEMORY.md 内容
          5. 写入 MEMORY.md，更新 dream cursor
        任一步骤异常均记录 warning 并返回 False，不传播异常。
        """
        started = time.monotonic()
        log_event(logger, logging.DEBUG, "dream.run.started")
        try:
            batch, updated_cursors = self._collect_new_entries()
        except Exception as exc:
            logger.warning(
                "Dream: failed to collect entries",
                exc_info=safe_exception_info(exc),
            )
            log_event(
                logger,
                logging.WARNING,
                "dream.run.failed",
                phase="collect",
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                error_type=type(exc).__name__,
            )
            return False

        if not batch:
            log_event(
                logger,
                logging.DEBUG,
                "dream.run.skipped",
                reason="no_new_entries",
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
            return False

        chat_count = len({entry.get("_chat_id") for entry in batch})
        log_event(
            logger,
            logging.INFO,
            "dream.run.processing",
            entry_count=len(batch),
            chat_count=chat_count,
        )

        entries_text = self._format_entries(batch)
        current_memory = self._store.read_memory()

        try:
            async with self._runtime.acquire_last() as snapshot:
                try:
                    analysis = await asyncio.wait_for(
                        self._phase1_analyze(snapshot, entries_text, current_memory),
                        timeout=self._operation_timeout,
                    )
                    logger.debug("Dream Phase 1 done (%d chars)", len(analysis))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._log_phase_failure("Phase 1", exc)
                    log_event(
                        logger,
                        logging.WARNING,
                        "dream.run.failed",
                        phase="analyze",
                        duration_ms=round((time.monotonic() - started) * 1000, 2),
                        error_type=type(exc).__name__,
                    )
                    return False

                try:
                    new_memory = await asyncio.wait_for(
                        self._phase2_update(snapshot, analysis, current_memory),
                        timeout=self._operation_timeout,
                    )
                    logger.debug("Dream Phase 2 done (%d chars)", len(new_memory))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._log_phase_failure("Phase 2", exc)
                    log_event(
                        logger,
                        logging.WARNING,
                        "dream.run.failed",
                        phase="update",
                        duration_ms=round((time.monotonic() - started) * 1000, 2),
                        error_type=type(exc).__name__,
                    )
                    return False

                if new_memory.strip():
                    self._store.write_memory(new_memory.strip())
                    logger.info("Dream: MEMORY.md updated (%d chars)", len(new_memory))
                else:
                    logger.info("Dream: no memory changes (Phase 2 returned empty)")

                try:
                    self._store.set_dream_cursors(updated_cursors)
                except Exception as exc:
                    logger.warning(
                        "Dream: failed to update dream cursors",
                        exc_info=safe_exception_info(exc),
                    )
                    log_event(
                        logger,
                        logging.WARNING,
                        "dream.cursor_update.failed",
                        error_type=type(exc).__name__,
                    )
                log_event(
                    logger,
                    logging.INFO,
                    "dream.run.completed",
                    entry_count=len(batch),
                    chat_count=chat_count,
                    memory_changed=bool(new_memory.strip()),
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                )
                return True
        except LLMNotConfiguredError:
            log_event(
                logger,
                logging.DEBUG,
                "dream.run.skipped",
                reason="llm_not_configured",
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
            return False
        except asyncio.CancelledError:
            log_event(
                logger,
                logging.INFO,
                "dream.run.cancelled",
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
            raise
        except Exception as exc:
            self._log_phase_failure("runtime acquisition", exc)
            log_event(
                logger,
                logging.WARNING,
                "dream.run.failed",
                phase="runtime_acquisition",
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                error_type=type(exc).__name__,
            )
            return False
