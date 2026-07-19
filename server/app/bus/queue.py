"""异步消息总线：入站（客户端 → Agent）和出站（Agent → 客户端）队列。"""
from __future__ import annotations

import asyncio

from .events import InboundMessage, OutboundMessage


class MessageBus:
    """由两个队列组成的简单消息总线，对应 spore 的 core.bus.queue 模式。"""

    def __init__(self) -> None:
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

    async def publish_inbound(self, msg: InboundMessage) -> None:
        await self.inbound.put(msg)

    async def consume_inbound(self) -> InboundMessage:
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        return await self.outbound.get()
