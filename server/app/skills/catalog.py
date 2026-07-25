from __future__ import annotations

import math
import hashlib
import os
import re
import shutil
import threading
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Iterable

from .loader import read_skill_package
from .models import Availability, SkillError, SkillRecord, SkillSource

TOKEN_RE = re.compile(r"[a-z0-9_.-]+|[\u4e00-\u9fff]", re.IGNORECASE)
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\)[^\s'\"<>]+")
POSIX_ABSOLUTE_PATH_RE = re.compile(r"(?<![\w.])/(?:[^/\s'\"<>]+/)*[^/\s'\"<>]*")
CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
MAX_INVALID_PACKAGES = 100
MAX_INVALID_ERRORS = 3
MAX_INVALID_DIRECTORY_CHARS = 80
MAX_INVALID_MESSAGE_CHARS = 240


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    tokens = TOKEN_RE.findall(lowered)
    compact = re.sub(r"\s+", "", lowered)
    tokens.extend(compact[i:i + 2] for i in range(max(0, len(compact) - 1)) if "\u4e00" <= compact[i] <= "\u9fff")
    return tokens


def _bounded_text(value: str, limit: int) -> str:
    cleaned = CONTROL_CHAR_RE.sub(" ", str(value)).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit - 3]}..."


def sanitize_skill_error(
    message: str,
    paths: Iterable[Path] = (),
    *,
    limit: int = MAX_INVALID_MESSAGE_CHARS,
) -> str:
    cleaned = WINDOWS_ABSOLUTE_PATH_RE.sub("<path>", str(message))
    cleaned = POSIX_ABSOLUTE_PATH_RE.sub("<path>", cleaned)
    variants: set[str] = set()
    for path in paths:
        variants.update((str(path), path.as_posix()))
        cleaned_path = str(path).replace("\\", "/")
        variants.add(cleaned_path)
    for variant in sorted(variants, key=len, reverse=True):
        if variant:
            cleaned = cleaned.replace(variant, "<path>")
    return _bounded_text(cleaned, max(4, limit)) or "invalid Skill package"


class SkillCatalog:
    """基于已校验元数据索引内置、用户和 Agent Skill。"""

    def __init__(
        self,
        builtin_root: Path,
        user_root: Path,
        agent_root: Path,
        *,
        tool_names: Callable[[], Iterable[str]] | None = None,
        mcp_servers: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        self.roots = {
            SkillSource.BUILTIN: builtin_root.resolve(),
            SkillSource.USER: user_root.resolve(),
            SkillSource.AGENT: agent_root.resolve(),
        }
        self._tool_names = tool_names or (lambda: ())
        self._mcp_servers = mcp_servers or (lambda: ())
        self._records: dict[str, SkillRecord] = {}
        self._invalid: dict[str, list[str]] = {}
        self._invalid_targets: dict[tuple[SkillSource, str], Path] = {}
        self._revision = 0
        self._lock = threading.RLock()
        self._document_tokens: dict[str, list[str]] = {}
        self.refresh()

    def set_runtime_sources(
        self,
        *,
        tool_names: Callable[[], Iterable[str]],
        mcp_servers: Callable[[], Iterable[str]],
    ) -> None:
        self._tool_names = tool_names
        self._mcp_servers = mcp_servers
        self.refresh()

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def invalid(self) -> dict[str, list[str]]:
        return {key: list(errors) for key, errors in self._invalid.items()}

    def invalid_target(self, source: SkillSource, directory: str) -> Path | None:
        with self._lock:
            return self._invalid_targets.get((source, directory))

    def refresh(self) -> None:
        with self._lock:
            candidates: dict[str, list[SkillRecord]] = defaultdict(list)
            invalid: dict[str, list[str]] = {}
            invalid_targets: dict[tuple[SkillSource, str], Path] = {}
            for source in (SkillSource.BUILTIN, SkillSource.USER, SkillSource.AGENT):
                root = self.roots[source]
                root.mkdir(parents=True, exist_ok=True)
                for child in sorted(root.iterdir(), key=lambda value: value.name.lower()):
                    if not child.is_dir() or child.name.startswith("."):
                        continue
                    try:
                        manifest, _, digest, meta = read_skill_package(child)
                        enabled = bool(meta.get("enabled", True))
                        record = SkillRecord(
                            manifest=manifest,
                            source=source,
                            path=child,
                            content_hash=digest,
                            enabled=enabled,
                        )
                        self._apply_availability(record)
                        candidates[manifest.name].append(record)
                    except (SkillError, OSError, UnicodeError) as exc:
                        if len(invalid) >= MAX_INVALID_PACKAGES:
                            continue
                        directory = _bounded_text(child.name, MAX_INVALID_DIRECTORY_CHARS) or "unknown"
                        key = f"{source.value}:{directory}"
                        if key in invalid:
                            suffix = hashlib.sha256(
                                child.name.encode("utf-8")
                            ).hexdigest()[:8]
                            prefix_limit = MAX_INVALID_DIRECTORY_CHARS - len(suffix) - 1
                            directory = f"{_bounded_text(child.name, prefix_limit)}~{suffix}"
                            key = f"{source.value}:{directory}"
                        invalid[key] = [
                            sanitize_skill_error(str(exc), (root, child))
                        ][:MAX_INVALID_ERRORS]
                        invalid_targets[(source, directory)] = child

            effective: dict[str, SkillRecord] = {}
            precedence = {SkillSource.BUILTIN: 0, SkillSource.USER: 1, SkillSource.AGENT: 2}
            for name, rows in candidates.items():
                rows.sort(key=lambda row: precedence[row.source])
                chosen = rows[-1]
                chosen.shadowed_sources = [row.source.value for row in rows[:-1]]
                effective[name] = chosen
            self._records = effective
            self._invalid = invalid
            self._invalid_targets = invalid_targets
            self._document_tokens = {
                name: _tokens(" ".join((
                    record.name,
                    record.display_name,
                    record.manifest.description,
                    " ".join(record.manifest.tags),
                    " ".join(record.manifest.triggers),
                )))
                for name, record in effective.items()
            }
            self._revision += 1

    def _apply_availability(self, record: SkillRecord) -> None:
        if not record.enabled:
            record.availability = Availability.DISABLED
            return
        required = record.manifest.requires
        tool_names = set(self._tool_names())
        configured_mcp = set(self._mcp_servers())
        missing: list[str] = []
        for binary in required.bins:
            if shutil.which(binary) is None:
                missing.append(f"bin:{binary}")
        for env_name in required.env:
            if not os.environ.get(env_name):
                missing.append(f"env:{env_name}")
        for tool in required.tools:
            if tool not in tool_names and not tool.startswith("mcp_"):
                missing.append(f"tool:{tool}")
        for server in required.mcp_servers:
            if server not in configured_mcp:
                missing.append(f"mcp:{server}")
        record.missing = missing
        record.availability = Availability.MISSING_DEPENDENCY if missing else Availability.AVAILABLE

    def get(self, name: str) -> SkillRecord | None:
        with self._lock:
            return self._records.get(name)

    def list(
        self,
        *,
        source: str | None = None,
        enabled: bool | None = None,
        availability: str | None = None,
    ) -> list[SkillRecord]:
        with self._lock:
            rows = list(self._records.values())
        if source:
            rows = [row for row in rows if row.source.value == source]
        if enabled is not None:
            rows = [row for row in rows if row.enabled is enabled]
        if availability:
            rows = [row for row in rows if row.availability.value == availability]
        return sorted(rows, key=lambda row: row.name)

    def search(
        self, query: str, limit: int = 8, *, include_disabled: bool = False
    ) -> list[tuple[float, SkillRecord]]:
        terms = _tokens(query)
        if not terms:
            return []
        with self._lock:
            documents = dict(self._document_tokens)
            records = dict(self._records)
        eligible = {
            name: tokens
            for name, tokens in documents.items()
            if include_disabled or records[name].enabled
        }
        if not eligible:
            return []
        doc_frequency = Counter()
        for tokens in eligible.values():
            doc_frequency.update(set(tokens))
        average_length = sum(map(len, eligible.values())) / len(eligible)
        scores: list[tuple[float, SkillRecord]] = []
        for name, tokens in eligible.items():
            counts = Counter(tokens)
            score = 0.0
            for term in terms:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                inverse = math.log(1 + (len(eligible) - doc_frequency[term] + 0.5) / (doc_frequency[term] + 0.5))
                denominator = frequency + 1.2 * (0.25 + 0.75 * len(tokens) / max(1, average_length))
                score += inverse * frequency * 2.2 / denominator
            if name == query.strip().lower():
                score += 10
            if score > 0:
                scores.append((score, records[name]))
        scores.sort(key=lambda row: (-row[0], row[1].name))
        return scores[:max(1, min(int(limit), 10_000))]

    def load_body(self, name: str) -> tuple[SkillRecord, str]:
        record = self.get(name)
        if record is None:
            raise SkillError(f"Skill not found: {name}")
        manifest, body, digest, _ = read_skill_package(record.path)
        if manifest.name != record.name or digest != record.content_hash:
            self.refresh()
            record = self.get(name)
            if record is None:
                raise SkillError(f"Skill changed during load: {name}")
            manifest, body, digest, _ = read_skill_package(record.path)
        return record, body
