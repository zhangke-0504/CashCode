"""集中解析并管理 CashCode 服务端使用的文件系统路径。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DataPaths:
    """集中保存运行数据目录及用户 MCP 配置文件路径。"""

    root: Path
    memory: Path
    mcp: Path
    mcp_servers: Path
    skills_user: Path
    skills_agent: Path
    skill_snapshots: Path
    skill_evolution: Path

    @classmethod
    def from_environment(cls, *, default_root: Path | None = None) -> "DataPaths":
        """根据 CASHCODE_DATA_DIR 或默认目录构造全部数据路径。"""

        fallback = default_root or (Path(__file__).resolve().parents[1] / "data")
        root = Path(os.environ.get("CASHCODE_DATA_DIR", str(fallback))).expanduser().resolve()
        return cls(
            root=root,
            memory=root / "memory",
            mcp=root / "mcp",
            mcp_servers=root / "mcp" / "servers.json",
            skills_user=root / "skills" / "user",
            skills_agent=root / "skills" / "agent",
            skill_snapshots=root / "skill-snapshots",
            skill_evolution=root / "skill-evolution",
        )

    def ensure(self) -> None:
        """创建运行所需的目录；具体 JSON 文件在首次写入时生成。"""

        for path in (
            self.root,
            self.memory,
            self.mcp,
            self.skills_user,
            self.skills_agent,
            self.skill_snapshots,
            self.skill_evolution,
        ):
            path.mkdir(parents=True, exist_ok=True)
