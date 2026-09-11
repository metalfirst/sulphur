"""
数据源包。

对外只暴露两个函数：
  - build_sources() -> list[Source]  根据配置构建源列表
  - fetch_all(days) -> list[dict]    并发抓取所有源，异常自吞

app.py 只依赖 fetch_all；新增源时：
  1. 在 sources/ 下新增模块（如 smm.py），继承 base.Source
  2. 在 build_sources() 里注册
  3. 如需新增可信度，把域名加到 config.SOURCE_CREDIBILITY
"""

from __future__ import annotations

import asyncio
import logging

from config import settings

from .base import Source, SourceError, make_item
from .gdelt import GdeltSource
from .rss import RssSource

logger = logging.getLogger("sulfur-news.sources")

__all__ = [
    "Source",
    "SourceError",
    "make_item",
    "GdeltSource",
    "RssSource",
    "build_sources",
    "fetch_all",
]


def build_sources() -> list[Source]:
    """按配置构建数据源列表。"""
    sources: list[Source] = []

    # GDELT：GDELT_API 非空即启用
    if settings.gdelt_api:
        sources.append(GdeltSource())

    # RSS：来自 .env 的 RSS_FEEDS（逗号分隔）
    for url in settings.rss_feeds:
        try:
            sources.append(RssSource(url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("跳过非法 RSS 源 %s：%s", url, exc)

    return sources


async def fetch_all(days: int) -> list[dict]:
    """
    并发抓取所有数据源，返回标准化条目列表。

    - 用 Semaphore 限制并发，避免瞬时打爆目标站点
    - 单个源失败只返回空列表，不影响整体
    - 顺序保持：先 GDELT，后按 RSS_FEEDS 顺序；下游还会再按时间排序
    """
    sources = build_sources()
    if not sources:
        logger.warning("没有配置任何数据源，返回空结果")
        return []

    sem = asyncio.Semaphore(max(1, settings.request_concurrency))

    async def run(src: Source) -> list[dict]:
        async with sem:
            return await src.safe_fetch(days)

    results = await asyncio.gather(*(run(s) for s in sources))
    flat: list[dict] = [item for sub in results for item in sub]
    logger.info("fetch_all 完成：%d 个源，共 %d 条原始条目", len(sources), len(flat))
    return flat
