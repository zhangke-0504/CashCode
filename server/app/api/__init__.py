# -*- coding: utf-8 -*-
"""HTTP 路由处理函数。"""

from .health import health
from .sessions import router as sessions_router
from .skills import router as skills_router
from .skill_evolution import router as skill_evolution_router
