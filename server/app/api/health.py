"""健康检查。"""


async def health():
    """健康检查端点。"""
    return {"status": "ok", "service": "cashcode"}
