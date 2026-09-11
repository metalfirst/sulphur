"""
定时刷新调度器。

对外接口：
  - refresh_news()      手动刷新一次，异常不抛出
  - start_scheduler()   启动后台循环，返回 asyncio.Task
  - stop_scheduler()    优雅停止

刷新链路：
  scheduler.refresh_news
      → services.aggregator.aggregate(days)
          → sources.fetch_all(days)
          → services.dedup / classifier / scorer
      → cache.commit(items)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from cache import cache
from config import settings

logger = logging.getLogger("sulfur-news.scheduler")


async def refresh_news() -> None:
    """抓取 + 处理 + 写缓存。任何异常都吞掉并写入 cache.last_error。"""
    if not cache.try_begin_update():
        logger.info("已有刷新任务执行中，跳过本次")
        return

    try:
        # 延迟导入：sources/services 可独立开发、独立测试
        from services.aggregator import aggregate

        logger.info("开始刷新：近 %d 天", settings.news_window_days)
        items = await aggregate(days=settings.news_window_days)
        cache.commit(items)
        logger.info("刷新成功：%d 条", len(items))
    except Exception as exc:  # noqa: BLE001
        cache.fail(str(exc))
        logger.exception("刷新失败：%s", exc)


async def _refresh_loop(interval_hours: float) -> None:
    # 启动时立即刷新一次
    await refresh_news()

    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)
            await refresh_news()
        except asyncio.CancelledError:
            logger.info("刷新循环收到取消信号，退出")
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("刷新循环异常：%s", exc)
            # 避免异常时高频重试
            await asyncio.sleep(60)


def start_scheduler() -> asyncio.Task:
    """启动后台刷新任务，返回 Task 供关闭时取消。"""
    task = asyncio.create_task(
        _refresh_loop(settings.refresh_interval_hours),
        name="sulfur-news-refresh-loop",
    )
    return task


async def stop_scheduler(task: Optional[asyncio.Task]) -> None:
    """优雅关闭后台刷新任务。"""
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
