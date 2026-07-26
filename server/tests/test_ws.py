"""
快速 WebSocket 测试客户端
用法: python test_ws.py [消息内容]
示例: python test_ws.py "给我讲个笑话"
"""
import asyncio
import json
import sys
import time

import websockets


WS_URL = "ws://127.0.0.1:8765/"


async def chat(message: str) -> None:
    async with websockets.connect(WS_URL) as ws:
        # 1. 等待 ready 帧，拿到 chat_id
        raw = await ws.recv()
        frame = json.loads(raw)
        assert frame["event"] == "ready", f"Expected ready, got: {frame}"
        chat_id = frame["chat_id"]
        print(f"[connected] chat_id={chat_id}\n")

        # 2. 发送消息
        await ws.send(json.dumps({
            "type": "message",
            "chat_id": chat_id,
            "content": message,
            "metadata": {"revert_keep_user_turns": 1},
        }))
        print(f"[you] {message}\n")
        print("[assistant] ", end="", flush=True)

        t0 = time.monotonic()

        # 3. 接收流式回复，直到 done
        async for raw in ws:
            frame = json.loads(raw)
            event = frame.get("event")

            if event == "delta":
                print(frame.get("text", ""), end="", flush=True)

            elif event == "stream_end":
                print()  # 换行

            elif event == "done":
                duration = frame.get("duration_sec", time.monotonic() - t0)
                print(f"\n[done] 耗时 {duration:.2f}s")
                break

            elif event == "error":
                print(f"\n[error] {frame.get('detail')}")
                break


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) or "你好，用一句话介绍一下自己"
    asyncio.run(chat(msg))
