"""CashCode Web 服务：FastAPI 服务器与 WebSocket 聊天通道。"""
import sys
import io
import asyncio
import argparse
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# 确保标准输出和标准错误使用 UTF-8 编码。
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 在其他代码读取 os.environ 前加载 .env。
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
import uvicorn

from app.api import health
from app.api.sessions import router as sessions_router
from app.bus.queue import MessageBus
from app.agent.loop import SimpleAgentLoop
from app.ws.channel import WebSocketChannel
from app.memory.dream import SimpleDream


# ---------------------------------------------------------------------------
# 全局状态（对应 spore 的 app.core.state 模式，此处为最简实现）
# ---------------------------------------------------------------------------
bus: MessageBus | None = None
agent: SimpleAgentLoop | None = None
ws_channel: WebSocketChannel | None = None
agent_task: asyncio.Task | None = None
ws_task: asyncio.Task | None = None
dream_task: asyncio.Task | None = None


async def _dream_loop(dream: SimpleDream) -> None:
    """Dream 后台定时任务：每隔 DREAM_INTERVAL 秒执行一次 Dream.run()。"""
    interval = int(os.environ.get("DREAM_INTERVAL", "300"))
    logger.info("Dream loop started (interval=%ds)", interval)
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await dream.run()
            except Exception:
                logger.warning("Dream: unhandled exception in run()", exc_info=True)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Dream loop stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时运行消息总线、Agent 循环、WebSocket 通道和 Dream 后台任务。"""
    global bus, agent, ws_channel, agent_task, ws_task, dream_task

    ws_host = os.environ.get("WS_HOST", "127.0.0.1")
    ws_port = int(os.environ.get("WS_PORT", "8765"))

    bus = MessageBus()
    agent = SimpleAgentLoop(bus)
    ws_channel = WebSocketChannel(bus, host=ws_host, port=ws_port)
    # Dream 复用 agent 的 client / model / store，无需额外初始化。
    dream = SimpleDream(agent._client, agent._model, agent._store)

    agent_task = asyncio.create_task(agent.run())
    ws_task = asyncio.create_task(ws_channel.start())
    dream_task = asyncio.create_task(_dream_loop(dream))

    logger.info("CashCode services started (WS on ws://%s:%d/)", ws_host, ws_port)

    try:
        yield
    finally:
        logger.info("Shutting down CashCode services...")
        if agent:
            agent.stop()
        if ws_channel:
            await ws_channel.stop()
        for task in (agent_task, ws_task, dream_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------
app = FastAPI(title="CashCode API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.get("/api/health")(health)
app.include_router(sessions_router, prefix="/api")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="HTTP server port")
    args = parser.parse_args()

    uvicorn.run(app, host="127.0.0.1", port=args.port)
