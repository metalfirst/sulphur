"""
聚合入口：把 raw sources → 去重 → 分类 → 打分 → NewsItem。

对外只暴露一个函数：
    async def aggregate(days: int) -> list[NewsItem]

流程：
  1. sources.fetch_all(days)             并发抓取
  2. 时间窗口过滤（双重保险）             保证只保留近 N 天
  3. services.dedup.dedup                去重
  4. services.classifier.classify_batch  分类 + 关键词
  5. services.scorer.score_batch         可信度
  6. 组装为 models.NewsItem              校验后返回
  7. 按发布时间倒序
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from models import NewsItem
from sources import fetch_all

from .classifier import classify_batch
from .dedup import dedup
from .scorer import score_batch

logger = logging.getLogger("sulfur-news.services.aggregator")


def _filter_window(items: list[dict], days: int) -> list[dict]:
    """按发布时间过滤近 N 天。sources 已做过一遍，这里再兜一次底。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept = []
    for it in items:
        ts = it.get("published_at")
        if not isinstance(ts, datetime):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
            it["published_at"] = ts
        if ts >= cutoff:
            kept.append(it)
    return kept


def _to_news_items(items: list[dict]) -> list[NewsItem]:
    """把 dict 转成 NewsItem，跳过校验失败的条目。"""
    out: list[NewsItem] = []
    failed = 0
    for it in items:
        try:
            out.append(NewsItem(**it))
        except ValidationError as exc:
            failed += 1
            logger.debug("条目校验失败，已跳过：%s | %s", it.get("url"), exc)
    if failed:
        logger.info("组装 NewsItem 跳过 %d 条校验失败数据", failed)
    return out


async def aggregate(days: int) -> list[NewsItem]:
    """完整聚合链路。"""
    # 1. 抓取
    raw = await fetch_all(days)
    if not raw:
        logger.warning("未抓取到任何原始条目")
        return []

    # 2. 时间过滤
    raw = _filter_window(raw, days)

    # 3. 去重
    unique = dedup(raw)

    # 4. 分类 + 关键词
    classify_batch(unique)

    # 5. 可信度
    score_batch(unique)

    # 6. 转成 NewsItem
    items = _to_news_items(unique)

    # 7. 排序（时间倒序），与前端展示顺序一致
    items.sort(key=lambda x: x.published_at, reverse=True)

    logger.info("聚合完成：%d 条", len(items))
    return items
