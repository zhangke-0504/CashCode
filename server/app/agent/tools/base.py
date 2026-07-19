"""Tool 抽象基类：定义所有 CashCode 工具的标准接口。

参考 spore ``core.agent.tools.base.Tool``，大幅简化：
- 去掉 Schema 验证体系（直接用 OpenAI function calling 的原生 JSON Schema）
- 去掉工具审批、hook 等复杂机制
- 保留最小接口：name / description / parameters / execute
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """CashCode 工具抽象基类。

    子类需实现 name、description、parameters()、execute()。
    to_openai_schema() 已提供默认实现，直接传给 OpenAI API 的 tools 参数。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，与 LLM tool_call 中的 function.name 对应。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """工具说明，LLM 依据此决定是否调用本工具。应清晰描述用途和触发时机。"""

    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """OpenAI JSON Schema 格式的参数定义。

        示例：
        {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "要保存的内容"}
            },
            "required": ["content"]
        }
        """

    def to_openai_schema(self) -> dict[str, Any]:
        """生成 OpenAI API tools 参数所需的完整 schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters(),
            },
        }

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """执行工具，返回结果字符串（供 LLM 读取）。

        失败时应返回描述错误的字符串，而非抛出异常。
        """
