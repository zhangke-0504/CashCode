# -*- coding: utf-8 -*-
"""V2 MCP 延迟激活体系：工具搜索、延迟注册表、激活集。

参考 spore:
  core.agent.tools.tool_search    — ToolSearchTool / ToolSearchIndex / DeferredAwareRegistry
  core.agent.mcp_tool_activation  — ActivatedToolSet / ContextVar 绑定
  core.agent.mcp_skill_activation_ctx — FullRegistry ContextVar

暴露的公共接口：
  ActivatedToolSet         LRU 激活集，持久化到 session metadata
  use_activated_set(set)   ContextVar 上下文管理器
  get_activated_set()      读取当前绑定
  DeferredAwareRegistry    包装 ToolRegistry，MCP 工具默认 deferred
  ToolSearchTool           内置工具：BM25 搜索 + 激活
  MCPPrepareTool           内置工具：按需连接 + 激活
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
from collections import Counter, OrderedDict, defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from .base import Tool
from .registry import ToolRegistry

import logging
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ActivatedToolSet
# ---------------------------------------------------------------------------

_METADATA_KEY = "activated_tools"
_DEFAULT_MAX_SIZE = 50


class ActivatedToolSet:
    """Session 级 LRU 激活集：{tool_name: last_touched_ts}。

    直接持有 session.metadata["activated_tools"] dict 的引用，
    写入即反映到 metadata，无需额外同步。
    """

    def __init__(self, data: dict[str, Any], max_size: int = _DEFAULT_MAX_SIZE) -> None:
        self._max_size = max(1, max_size)
        pairs = [(k, v) for k, v in data.items() if isinstance(k, str)]
        pairs.sort(key=lambda kv: kv[1] if isinstance(kv[1], (int, float)) else 0)
        self._data: OrderedDict[str, float] = OrderedDict(pairs)
        self._visibility_revision = 0
        self._raw: dict[str, Any] = data  # metadata 子dict 的引用，写入即持久化

    @classmethod
    def from_session(cls, metadata: dict[str, Any], max_size: int = _DEFAULT_MAX_SIZE) -> "ActivatedToolSet":
        raw = metadata.setdefault(_METADATA_KEY, {})
        if not isinstance(raw, dict):
            raw = {}
            metadata[_METADATA_KEY] = raw
        return cls(raw, max_size=max_size)

    def activate(self, name: str) -> None:
        if name in self._data:
            self.touch(name)
            return
        now = time.time()
        self._data[name] = now
        self._raw[name] = now
        while len(self._data) > self._max_size:
            evicted, _ = self._data.popitem(last=False)
            self._raw.pop(evicted, None)
        self._visibility_revision += 1

    def touch(self, name: str) -> None:
        if name not in self._data:
            return
        now = time.time()
        self._data.move_to_end(name)
        self._data[name] = now
        self._raw[name] = now

    def deactivate(self, name: str) -> None:
        if self._data.pop(name, None) is not None:
            self._raw.pop(name, None)
            self._visibility_revision += 1

    def is_activated(self, name: str) -> bool:
        return name in self._data

    def activated_names(self) -> frozenset[str]:
        return frozenset(self._data.keys())

    @property
    def visibility_revision(self) -> int:
        return self._visibility_revision

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, name: str) -> bool:
        return name in self._data


# ---------------------------------------------------------------------------
# ContextVar 绑定
# ---------------------------------------------------------------------------

_current_activated_set: ContextVar["ActivatedToolSet | None"] = ContextVar(
    "mcp_current_activated_set", default=None
)


@contextmanager
def use_activated_set(activated_set: "ActivatedToolSet") -> Iterator[None]:
    """将 activated_set 绑定到当前 async task（含子 task）。"""
    token = _current_activated_set.set(activated_set)
    try:
        yield
    finally:
        _current_activated_set.reset(token)


def get_activated_set() -> "ActivatedToolSet | None":
    return _current_activated_set.get()


# ---------------------------------------------------------------------------
# DeferredAwareRegistry
# ---------------------------------------------------------------------------

class DeferredAwareRegistry(ToolRegistry):
    """包装 FullRegistry，MCP 工具默认 deferred（对 LLM 不可见）。

    get_definitions() 每次调用都从 ActivatedToolSet 动态计算可见工具列表，
    缓存 key 包含 activation_revision，激活后立即生效。
    """

    def __init__(self, full_registry: ToolRegistry) -> None:
        super().__init__()
        self._full = full_registry
        self._projection_cache_key: tuple | None = None

    def _is_deferred(self, name: str) -> bool:
        return name.startswith("mcp_")

    def get_definitions(self) -> list[dict[str, Any]]:
        activated_set = get_activated_set()
        activated_names = activated_set.activated_names() if activated_set else frozenset()
        activation_rev = activated_set.visibility_revision if activated_set else -1
        cache_key = (self._full.membership_revision, activation_rev, self._membership_revision)
        if self._projection_cache_key == cache_key and self._cached_definitions is not None:
            return self._cached_definitions

        definitions: list[dict] = []
        seen: set[str] = set()
        # Pass 1: 本 registry 的工具（tool_search、mcp_prepare 等 builtin）
        for name, tool in self._tools.items():
            definitions.append(tool.to_schema())
            seen.add(name)
        # Pass 2: FullRegistry 的工具，deferred 工具只在激活集中才可见
        for name in self._full.tool_names:
            if name in seen:
                continue
            tool = self._full.get(name)
            if tool is None:
                continue
            if not self._is_deferred(name) or name in activated_names:
                definitions.append(tool.to_schema())

        builtins = [s for s in definitions if not self._schema_name(s).startswith("mcp_")]
        mcp_tools = [s for s in definitions if self._schema_name(s).startswith("mcp_")]
        builtins.sort(key=self._schema_name)
        mcp_tools.sort(key=self._schema_name)
        self._cached_definitions = builtins + mcp_tools
        self._projection_cache_key = cache_key
        return self._cached_definitions

    def prepare_call(self, name: str, params: dict) -> tuple:
        if name in self._tools:
            return super().prepare_call(name, params)
        if self._is_deferred(name):
            activated_set = get_activated_set()
            if activated_set is not None and name in activated_set:
                return self._full.prepare_call(name, params)
            msg = (
                f"工具 '{name}' 已注册但尚未激活。请先调用 tool_search 搜索相关工具，"
                "系统会自动将命中的工具加入激活集，之后即可直接调用。"
                "\n\n[Analyze the error above and try a different approach.]"
            )
            return None, params, msg
        return self._full.prepare_call(name, params)

    async def execute(self, name: str, params: dict) -> Any:
        if name in self._tools:
            return await super().execute(name, params)
        if self._is_deferred(name):
            activated_set = get_activated_set()
            if activated_set is not None and name in activated_set:
                result = await self._full.execute(name, params)
                activated_set.touch(name)
                return result
            return (
                f"工具 '{name}' 尚未激活，无法执行。"
                "\n\n[Analyze the error above and try a different approach.]"
            )
        result = await self._full.execute(name, params)
        if name.startswith("mcp_"):
            activated_set = get_activated_set()
            if activated_set is not None:
                activated_set.touch(name)
        return result

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name) or self._full.get(name)

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    @property
    def tool_names(self) -> list[str]:
        names = list(self._full.tool_names)
        for n in self._tools:
            if n not in names:
                names.append(n)
        return names

    @property
    def membership_revision(self) -> int:
        return (self._full.membership_revision << 32) + self._membership_revision


# ---------------------------------------------------------------------------
# 数据容器
# ---------------------------------------------------------------------------

@dataclass
class ServiceMeta:
    server_name: str
    display_name: str = ""
    description: str = ""


@dataclass
class ToolMeta:
    name: str              # wrapped name: mcp_server_tool
    original_name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class IndexDocument:
    server_name: str
    service_meta: ServiceMeta
    tool_meta: "ToolMeta | None"
    search_text: str
    source: str = "cache"        # "live" | "cache"
    callable: bool = True        # False = cache-only, needs mcp_prepare
    requires_preparation: bool = False


# ---------------------------------------------------------------------------
# 分词器（搬运 spore tool_search.py）
# ---------------------------------------------------------------------------

_CJK_RANGES = (
    (0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x20000, 0x2A6DF),
    (0x2A700, 0x2B73F), (0xF900, 0xFAFF), (0x3000, 0x303F),
    (0x3040, 0x309F), (0x30A0, 0x30FF), (0xFF00, 0xFFEF),
)


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def _camel_split(token: str) -> list[str]:
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", token)
    parts = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", parts)
    return [p.lower() for p in parts.split() if p]


def _ascii_tokens(text: str) -> list[str]:
    raw = re.split(r"[^A-Za-z0-9]+", text)
    out: list[str] = []
    for part in raw:
        if not part:
            continue
        out.extend(_camel_split(part) or [part.lower()])
    return [t for t in out if len(t) >= 2]


def _cjk_bigrams(text: str) -> list[str]:
    bigrams: list[str] = []
    run = ""
    for ch in text:
        if _is_cjk(ch):
            run += ch
        else:
            if len(run) >= 2:
                bigrams.extend(run[i:i+2] for i in range(len(run) - 1))
            run = ""
    if len(run) >= 2:
        bigrams.extend(run[i:i+2] for i in range(len(run) - 1))
    return bigrams


def tokenize(text: str) -> list[str]:
    tokens = _ascii_tokens(text)
    tokens.extend(_cjk_bigrams(text))
    return tokens


# ---------------------------------------------------------------------------
# ToolSearchIndex — BM25（k1=1.5, b=0.75）
# ---------------------------------------------------------------------------

_BM25_K1 = 1.5
_BM25_B  = 0.75


def _docs_fingerprint(docs: list[IndexDocument]) -> str:
    parts = []
    for d in docs:
        key = d.tool_meta.name if d.tool_meta else d.server_name
        parts.append(f"{d.server_name}:{key}:{d.source}:{d.callable}:{d.search_text}")
    return hashlib.md5("|".join(sorted(parts)).encode()).hexdigest()[:16]


class ToolSearchIndex:
    """内存 BM25 索引，内容未变时不重建（fingerprint 缓存）。"""

    def __init__(self) -> None:
        self._docs: list[IndexDocument] = []
        self._fingerprint: str = ""
        self._inverted: dict[str, dict[int, int]] = {}
        self._doc_lengths: list[int] = []
        self._avg_doc_length: float = 0.0
        self._df: dict[str, int] = {}
        self._n_docs: int = 0

    def _rebuild(self, docs: list[IndexDocument]) -> None:
        self._docs = docs
        self._n_docs = len(docs)
        self._inverted = defaultdict(dict)
        self._df = {}
        self._doc_lengths = []
        for idx, doc in enumerate(docs):
            terms = tokenize(doc.search_text)
            self._doc_lengths.append(len(terms))
            tf: Counter[str] = Counter(terms)
            for term, cnt in tf.items():
                self._inverted[term][idx] = cnt
            for term in set(terms):
                self._df[term] = self._df.get(term, 0) + 1
        self._avg_doc_length = sum(self._doc_lengths) / self._n_docs if self._n_docs else 0.0

    def ensure_fresh(self, docs: list[IndexDocument]) -> None:
        fp = _docs_fingerprint(docs)
        if fp != self._fingerprint:
            self._rebuild(docs)
            self._fingerprint = fp

    def search(self, query: str, *, limit: int = 8) -> list[tuple[float, IndexDocument]]:
        q_terms = tokenize(query)
        if not q_terms or not self._docs:
            return []
        scores: dict[int, float] = defaultdict(float)
        n = self._n_docs
        k1, b, avg_dl = _BM25_K1, _BM25_B, self._avg_doc_length
        for term in q_terms:
            if term not in self._inverted:
                continue
            df = self._df.get(term, 0)
            idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
            for idx, tf in self._inverted[term].items():
                dl = self._doc_lengths[idx]
                tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl)) if avg_dl else tf
                scores[idx] += idf * tf_norm
        results: list[tuple[float, IndexDocument]] = []
        for idx, score in sorted(scores.items(), key=lambda kv: -kv[1]):
            results.append((score, self._docs[idx]))
            if len(results) >= limit:
                break
        return results


# ---------------------------------------------------------------------------
# CacheFeeder — 合并 disk cache + live ToolRegistry
# ---------------------------------------------------------------------------

class CacheFeeder:
    """从 disk cache + live ToolRegistry 构建 IndexDocument 列表。"""

    def __init__(self, mcp_servers: dict, registry: ToolRegistry) -> None:
        self._servers = mcp_servers
        self._registry = registry

    def iter_documents(self) -> list[IndexDocument]:
        from .mcp_cache import read_cache

        docs: list[IndexDocument] = []
        for server_name, cfg in self._servers.items():
            if not isinstance(cfg, dict):
                continue
            display_name = cfg.get("display_name") or server_name
            description  = cfg.get("description") or ""

            # 读 live registry（已连接 server 的 wrapper）
            live_tools: dict[str, dict] = {}
            prefix = f"mcp_{server_name}_"
            for tool_name in self._registry.tool_names:
                if not tool_name.startswith(prefix):
                    continue
                tool_obj = self._registry.get(tool_name)
                if tool_obj is None:
                    continue
                raw_name = getattr(tool_obj, "_original_name", tool_name[len(prefix):])
                live_tools[raw_name] = {
                    "name": raw_name,
                    "description": getattr(tool_obj, "description", ""),
                    "inputSchema": getattr(tool_obj, "parameters", lambda: {})(),
                    "wrapped_name": tool_name,
                }

            # 读 disk cache
            cached = read_cache(server_name, cfg)
            cached_tools = {t["name"]: t for t in (cached or [])}

            # 合并：live 优先
            all_tools: dict[str, tuple[dict, str, bool]] = {}
            for raw_name, t in cached_tools.items():
                all_tools[raw_name] = (t, "cache", False)
            for raw_name, t in live_tools.items():
                all_tools[raw_name] = (t, "live", True)

            svc = ServiceMeta(server_name=server_name, display_name=display_name, description=description)
            for raw_name, (t, source, is_callable) in all_tools.items():
                desc = t.get("description") or ""
                wrapped = t.get("wrapped_name") or f"mcp_{server_name}_{raw_name}"
                search_text = " ".join(filter(None, [
                    display_name, description, raw_name,
                    " ".join(_camel_split(raw_name)), desc,
                ]))
                docs.append(IndexDocument(
                    server_name=server_name,
                    service_meta=svc,
                    tool_meta=ToolMeta(name=wrapped, original_name=raw_name,
                                       description=desc, input_schema=t.get("inputSchema") or {}),
                    search_text=search_text,
                    source=source,
                    callable=is_callable,
                    requires_preparation=not is_callable,
                ))

            # 若该 server 没有任何工具（无 cache 也无 live 连接），
            # 仍生成一个服务级存根，使 tool_search 能找到它并引导 mcp_prepare
            if not all_tools:
                search_text = " ".join(filter(None, [
                    server_name, display_name, description,
                ]))
                docs.append(IndexDocument(
                    server_name=server_name,
                    service_meta=svc,
                    tool_meta=None,        # 服务级，无具体工具
                    search_text=search_text,
                    source="config",
                    callable=False,
                    requires_preparation=True,
                ))
        return docs


# ---------------------------------------------------------------------------
# ToolSearchTool
# ---------------------------------------------------------------------------

class ToolSearchTool(Tool):
    """内置工具：BM25 搜索 MCP 工具并激活命中结果。永远对 LLM 可见（非 deferred）。"""

    def __init__(self, full_registry: ToolRegistry, mcp_servers: dict) -> None:
        self._registry = full_registry
        self._mcp_servers = mcp_servers
        self._index = ToolSearchIndex()

    @property
    def name(self) -> str:
        return "tool_search"

    @property
    def description(self) -> str:
        return (
            "搜索可用的 MCP 工具。当你需要使用某个功能但不确定工具名称时，先调用此工具搜索。"
            "命中的工具会自动激活，下一轮可直接调用。"
            "支持中文关键词、工具名称、服务名称、功能描述等多种搜索方式。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词，支持中文、工具名、服务名、功能描述"},
                "limit": {"type": "integer", "description": "返回结果上限，默认8", "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        }

    async def execute(self, query: str = "", limit: int = 8, **_: Any) -> str:
        if not query.strip():
            return "请提供搜索关键词。"
        docs = CacheFeeder(self._mcp_servers, self._registry).iter_documents()
        self._index.ensure_fresh(docs)
        hits = self._index.search(query, limit=min(int(limit), 50))
        if not hits:
            return f"未找到与「{query}」相关的工具。建议换用不同关键词后重试。"

        activated_set = get_activated_set()
        lines = [f"## 搜索结果：{query}\n"]
        newly_activated: list[str] = []
        for score, doc in hits:
            if doc.tool_meta is None:
                # 服务级存根：server 已配置但未连接，引导 mcp_prepare
                svc = doc.service_meta
                header = svc.display_name or doc.server_name
                desc = f"：{svc.description}" if svc.description else ""
                lines.append(f"### {header}{desc}")
                lines.append(
                    f"  此服务已配置但尚未建立连接，请先调用 `mcp_prepare` 连接：\n"
                    f"  `mcp_prepare(server_name=\"{doc.server_name}\")`"
                )
                lines.append("")
                continue
            tool_name = doc.tool_meta.name
            desc = doc.tool_meta.description or "(暂无描述)"
            if doc.requires_preparation or not doc.callable:
                code = doc.server_name
                lines.append(f"- **{doc.tool_meta.original_name}**: {desc}")
                lines.append(f"  (requiresPreparation; 请用 `mcp_prepare(server_name=\"{code}\")` 连接后再调用)")
                continue
            lines.append(f"- **{tool_name}**: {desc}")
            if self._registry.has(tool_name) and activated_set is not None:
                if tool_name not in activated_set:
                    activated_set.activate(tool_name)
                    newly_activated.append(tool_name)
        if newly_activated:
            lines.append(f"\n✅ **{len(newly_activated)} 个工具已激活，本会话内可直接调用：**")
            lines.extend(f"  - {t}" for t in newly_activated)
        result = "\n".join(lines).strip()
        return result if result != f"## 搜索结果：{query}" else f"未找到与「{query}」相关的工具。"


# ---------------------------------------------------------------------------
# MCPPrepareTool
# ---------------------------------------------------------------------------

class MCPPrepareTool(Tool):
    """内置工具：按需建立 MCP server 连接并激活其工具。永远对 LLM 可见（非 deferred）。

    prepare_callback: async (server_name) -> bool
        由 loop.py 注入，负责调用 lazy_connect + list_tools + write_cache + register wrappers。
        返回 True 表示成功，False 表示失败。
    registry: ToolRegistry
        FullRegistry，prepare_callback 成功后从中取已注册的 wrapper 并激活。
    """

    def __init__(
        self,
        prepare_callback: "Callable[[str], Any]",
        registry: ToolRegistry,
    ) -> None:
        self._prepare = prepare_callback
        self._registry = registry

    @property
    def name(self) -> str:
        return "mcp_prepare"

    @property
    def description(self) -> str:
        return (
            "按需连接一个 MCP server 并激活其工具。"
            "当 tool_search 返回 requiresPreparation 提示时，调用此工具传入 server_name。"
            "连接成功后工具自动激活，可直接调用。"
        )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "mcp_config.json 中的 server key，如 'weather'"},
            },
            "required": ["server_name"],
        }

    async def execute(self, server_name: str = "", **_: Any) -> str:
        name = (server_name or "").strip()
        if not name:
            return "Error: server_name 不能为空。"
        try:
            ok = await self._prepare(name)
        except Exception as exc:
            logger.warning("MCPPrepareTool: prepare('%s') raised: %s", name, exc)
            return f"Error: 连接 MCP server '{name}' 失败：{type(exc).__name__}: {exc}"
        if not ok:
            return f"Error: 连接 MCP server '{name}' 失败，请检查配置。"

        # 激活刚注册的工具
        activated_set = get_activated_set()
        prefix = f"mcp_{name}_"
        activated: list[str] = []
        for tool_name in self._registry.tool_names:
            if tool_name.startswith(prefix):
                if activated_set is not None:
                    activated_set.activate(tool_name)
                activated.append(tool_name)
        if activated:
            return (
                f"MCP server '{name}' 已连接。"
                f"已激活 {len(activated)} 个工具：{', '.join(activated)}"
            )
        return f"MCP server '{name}' 已连接，但未发现任何工具。"
