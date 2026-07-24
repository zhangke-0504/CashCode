from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from .catalog import SkillCatalog
from .loader import parse_skill_text
from .models import SkillConflictError, SkillError, SkillSource
from .store import SkillStore

logger = logging.getLogger(__name__)
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"
)


@dataclass(frozen=True, slots=True)
class EvolutionConfig:
    enabled: bool = False
    min_tool_calls: int = 2
    recurrence: int = 2
    max_context_chars: int = 12_000
    max_concurrent: int = 1
    max_evidence: int = 500

    @classmethod
    def from_environment(cls) -> "EvolutionConfig":
        return cls(
            enabled=os.environ.get("SKILL_EVOLUTION_ENABLED", "false").lower() in {"1", "true", "yes"},
            min_tool_calls=max(1, int(os.environ.get("SKILL_EVOLUTION_MIN_TOOL_CALLS", "2"))),
            recurrence=max(2, int(os.environ.get("SKILL_EVOLUTION_RECURRENCE", "2"))),
            max_context_chars=max(1000, int(os.environ.get("SKILL_EVOLUTION_MAX_CONTEXT_CHARS", "12000"))),
            max_concurrent=max(1, int(os.environ.get("SKILL_EVOLUTION_MAX_CONCURRENT", "1"))),
            max_evidence=max(10, int(os.environ.get("SKILL_EVOLUTION_MAX_EVIDENCE", "500"))),
        )


@dataclass(slots=True)
class EvolutionProposal:
    id: str
    action: str
    name: str
    candidate_content: str
    reason: str
    evidence_ids: list[str]
    base_hash: str | None = None
    status: str = "pending"
    validation: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    applied_version: str | None = None


class EvolutionService:
    """默认关闭的证据收集器，只生成待审自进化提案。"""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        catalog: SkillCatalog,
        skill_store: SkillStore,
        root: Path,
        config: EvolutionConfig | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.catalog = catalog
        self.skill_store = skill_store
        self.root = root.resolve()
        self.evidence_root = self.root / "evidence"
        self.proposal_root = self.root / "proposals"
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.proposal_root.mkdir(parents=True, exist_ok=True)
        self.config = config or EvolutionConfig.from_environment()
        self._gate = asyncio.Semaphore(self.config.max_concurrent)
        self._tasks: set[asyncio.Task] = set()

    def schedule_turn(
        self,
        *,
        chat_id: str,
        user_content: str,
        final_content: str,
        tools_used: list[str],
        durable_messages: list[dict[str, Any]],
        persisted: bool,
    ) -> None:
        if not self.config.enabled or not persisted or len(tools_used) < self.config.min_tool_calls:
            return
        task = asyncio.create_task(self._consider_turn(
            chat_id=chat_id,
            user_content=user_content,
            final_content=final_content,
            tools_used=tools_used,
            durable_messages=durable_messages,
        ))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    @staticmethod
    def _sanitize(text: str, limit: int) -> str:
        value = SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
        value = re.sub(r"\[Skill loaded:.*?\]", "[Skill loaded receipt]", value)
        return value[:limit]

    def _fingerprint(self, user_content: str, tools_used: list[str]) -> str:
        normalized = re.sub(r"\b\d+\b", "#", user_content.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()[:500]
        material = normalized + "|" + "|".join(sorted(set(tools_used)))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]

    def _write_json(self, path: Path, value: dict[str, Any]) -> None:
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)

    async def _consider_turn(
        self,
        *,
        chat_id: str,
        user_content: str,
        final_content: str,
        tools_used: list[str],
        durable_messages: list[dict[str, Any]],
    ) -> None:
        async with self._gate:
            fingerprint = self._fingerprint(user_content, tools_used)
            evidence_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
            evidence = {
                "id": evidence_id,
                "fingerprint": fingerprint,
                "chat_id_hash": hashlib.sha256(chat_id.encode()).hexdigest()[:12],
                "user": self._sanitize(user_content, 2000),
                "assistant": self._sanitize(final_content, 2500),
                "tools": list(tools_used),
                "tool_receipts": [
                    self._sanitize(str(message.get("content", "")), 500)
                    for message in durable_messages
                    if message.get("role") == "tool"
                ],
                "created_at": time.time(),
            }
            self._write_json(self.evidence_root / f"{evidence_id}.json", evidence)
            self._prune_evidence()
            matches = []
            for path in self.evidence_root.glob("*.json"):
                try:
                    row = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if row.get("fingerprint") == fingerprint:
                    matches.append(row)
            if len(matches) < self.config.recurrence or self._has_open_fingerprint(fingerprint):
                return
            await self._generate_proposal(matches[-self.config.recurrence:], fingerprint)

    def _prune_evidence(self) -> None:
        paths = sorted(
            self.evidence_root.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in paths[self.config.max_evidence:]:
            path.unlink(missing_ok=True)

    def _has_open_fingerprint(self, fingerprint: str) -> bool:
        for path in self.proposal_root.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if row.get("fingerprint") == fingerprint and row.get("status") in {"pending", "applied"}:
                return True
        return False

    async def _generate_proposal(self, evidence: list[dict[str, Any]], fingerprint: str) -> None:
        summaries = [record.to_dict() for record in self.catalog.list()[:80]]
        creator = self.catalog.get("skill-creator")
        contract = ""
        if creator:
            _, contract = self.catalog.load_body("skill-creator")
        prompt = {
            "contract": contract[:5000],
            "existing_skills": summaries,
            "evidence": evidence,
            "rules": [
                "Return JSON only.",
                "Use action 'create' or 'update'. Updates may target only source=agent.",
                "candidate_content must be a complete SKILL.md with YAML frontmatter.",
                "Do not save one-off identifiers, failures, secrets, or project status.",
                "At most one conceptual Skill proposal.",
            ],
        }
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a restricted Skill proposal generator. You cannot modify files or call tools."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)[:self.config.max_context_chars]},
            ],
            stream=False,
        )
        raw = response.choices[0].message.content or ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Evolution proposal was not valid JSON")
            return
        if not isinstance(data, dict) or data.get("action") not in {"create", "update"}:
            return
        name = str(data.get("name") or "")
        candidate = str(data.get("candidate_content") or "")
        validation: dict[str, Any]
        try:
            parse_skill_text(candidate, expected_name=name)
            validation = {"valid": True, "errors": []}
        except SkillError as exc:
            validation = {"valid": False, "errors": [str(exc)]}
        target = self.catalog.get(name)
        if data["action"] == "update" and (target is None or target.source is not SkillSource.AGENT):
            return
        proposal = EvolutionProposal(
            id=uuid.uuid4().hex,
            action=data["action"],
            name=name,
            candidate_content=candidate,
            reason=str(data.get("reason") or "Reusable workflow evidence"),
            evidence_ids=[row["id"] for row in evidence],
            base_hash=target.content_hash if target else None,
            validation=validation,
        )
        payload = asdict(proposal)
        payload["fingerprint"] = fingerprint
        self._write_json(self.proposal_root / f"{proposal.id}.json", payload)

    def list_proposals(self) -> list[dict[str, Any]]:
        rows = []
        for path in self.proposal_root.glob("*.json"):
            try:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        rows.sort(key=lambda row: row.get("created_at", 0), reverse=True)
        return rows

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        path = self.proposal_root / f"{proposal_id}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def reject(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            raise SkillError("proposal not found")
        if proposal.get("status") != "pending":
            raise SkillConflictError("proposal is not pending")
        proposal["status"] = "rejected"
        proposal["updated_at"] = time.time()
        self._write_json(self.proposal_root / f"{proposal_id}.json", proposal)
        return proposal

    def approve(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get_proposal(proposal_id)
        if proposal is None:
            raise SkillError("proposal not found")
        if proposal.get("status") != "pending":
            raise SkillConflictError("proposal is not pending")
        if not proposal.get("validation", {}).get("valid"):
            raise SkillError("proposal candidate is invalid")
        if proposal["action"] == "create":
            result = self.skill_store.create(
                proposal["name"], proposal["candidate_content"], source=SkillSource.AGENT
            )
        else:
            result = self.skill_store.replace(
                proposal["name"],
                proposal["candidate_content"],
                expected_hash=proposal.get("base_hash"),
                evolution=True,
            )
        proposal["status"] = "applied"
        proposal["updated_at"] = time.time()
        proposal["applied_version"] = str(result.get("version") or result.get("snapshot") or "")
        self._write_json(self.proposal_root / f"{proposal_id}.json", proposal)
        return proposal
