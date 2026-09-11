"""
FastAPI 入口。

职责限定为：
  1. 生命周期（启动/关闭调度器）
  2. CORS、静态文件等中间件
  3. REST 路由：/api/news、/api/categories、/api/health、/api/refresh
  4. 从前端/客户端视角组装响应模型

业务逻辑（抓取、去重、分类、评分）全部在 sources/ 与 services/ 中。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from cache import cache
from config import CATEGORY_KEYWORDS, settings
from models import (
    CategoriesResponse,
    HealthResponse,
    NewsResponse,
    RefreshResponse,
)
from scheduler import refresh_news, start_scheduler, stop_scheduler

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sulfur-news")


# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = start_scheduler()
    app.state.refresh_task = task
    logger.info(
        "调度器已启动：窗口 %d 天，间隔 %.1f 小时",
        settings.news_window_days,
        settings.refresh_interval_hours,
    )
    try:
        yield
    finally:
        await stop_scheduler(task)
        logger.info("调度器已停止")


# ---------------------------------------------------------------------------
# 应用
# ---------------------------------------------------------------------------
app = FastAPI(
    title="硫磺新闻聚合 API",
    description="聚合近 15 天硫磺相关的价格行情、产业动态、政策法规、进出口贸易新闻。",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """健康检查 + 缓存状态。"""
    return HealthResponse(
        status="ok",
        items=len(cache.items),
        last_updated=cache.last_updated,
        updating=cache.updating,
        last_error=cache.last_error,
        window_days=settings.news_window_days,
    )


@app.get("/api/categories", response_model=CategoriesResponse, tags=["meta"])
async def list_categories() -> CategoriesResponse:
    """返回支持的分类列表。"""
    return CategoriesResponse(categories=list(CATEGORY_KEYWORDS.keys()))


@app.get("/api/news", response_model=NewsResponse, tags=["news"])
async def get_news(
    category: Optional[str] = Query(None, description="分类过滤"),
    q: Optional[str] = Query(None, description="标题/摘要关键词搜索"),
    limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
) -> NewsResponse:
    """
    返回近 N 天新闻，按发布时间倒序。

    - category: 价格行情 / 产业动态 / 政策法规 / 进出口贸易
    - q: 大小写不敏感子串匹配
    """
    items = cache.items

    if category:
        if category not in CATEGORY_KEYWORDS:
            raise HTTPException(
                status_code=400,
                detail=f"未知分类 '{category}'，可选：{list(CATEGORY_KEYWORDS)}",
            )
        items = [i for i in items if i.category.value == category]

    if q:
        needle = q.lower()
        items = [
            i
            for i in items
            if needle in i.title.lower()
            or needle in (i.summary or "").lower()
        ]

    items = items[:limit]

    return NewsResponse(
        items=items,
        total=len(items),
        last_updated=cache.last_updated,
        window_days=settings.news_window_days,
    )


@app.get("/api/news/{category}", response_model=NewsResponse, tags=["news"])
async def get_news_by_category(
    category: str,
    limit: int = Query(100, ge=1, le=500),
) -> NewsResponse:
    """语义化路由，等价于 /api/news?category=xxx。"""
    return await get_news(category=category, q=None, limit=limit)


@app.post("/api/refresh", response_model=RefreshResponse, tags=["admin"])
async def manual_refresh() -> RefreshResponse:
    """手动触发一次刷新（调试 / 运维用）。"""
    if cache.updating:
        raise HTTPException(status_code=429, detail="刷新正在进行中，请稍后再试")

    await refresh_news()
    ok = cache.last_error is None
    return RefreshResponse(
        status="ok" if ok else "error",
        count=len(cache.items),
        last_updated=cache.last_updated,
        error=cache.last_error,
    )


# ---------------------------------------------------------------------------
# 静态前端（可选）
# ---------------------------------------------------------------------------
_frontend = settings.frontend_dir

if _frontend.is_dir():
    app.mount("/static", StaticFiles(directory=str(_frontend)), name="static")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(str(_frontend / "index.html"))
else:
    logger.warning("前端目录不存在，跳过静态文件挂载：%s", _frontend)

    @app.get("/", include_in_schema=False)
    async def index_fallback():
        return {
            "message": "API is running. Frontend not found.",
            "docs": "/docs",
            "health": "/api/health",
        }


# ---------------------------------------------------------------------------
# 本地调试入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )