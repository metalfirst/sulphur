"""
数据源基类与通用工具。

约定：
  - 所有源最终产出 "标准条目"（dict），至少包含：
      title, url, source, domain, published_at, summary
  - 源只负责抓取与字段归一化，不做去重/分类/评分（那是 services/ 的职责）
  - 抓取异常用 SourceError 包装，由 __init__.fetch_all 统一兜底
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("sulfur-news.sources")


class SourceError(Exception):
    """源级别的抓取/解析错误。"""


def make_item(
    *,
    title: str,
    url: str,
    source: str = "",
    domain: str = "",
    published_at: datetime | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """
    构造一条标准化原始条目。

    - title / url 为空时抛 ValueError
    - published_at 缺省用当前 UTC 时间
    - summary 为空字符串时归一化为 None
    """
    title = (title or "").strip()
    url = (url or "").strip()
    if not title or not url:
        raise ValueError("title 和 url 不能为空")

    return {
        "title": title,
        "url": url,
        "source": (source or "").strip(),
        "domain": (domain or "").strip().lower(),
        "published_at": published_at or datetime.now(timezone.utc),
        "summary": (summary or "").strip() or None,
    }


class Source(ABC):
    """所有数据源的抽象基类。"""

    #: 子类应覆写为有意义的名称，用于日志和调试
    name: str = "source"

    @abstractmethod
    async def fetch(self, days: int) -> list[dict[str, Any]]:
        """抓取最近 `days` 天的条目，返回标准化 dict 列表。"""
        raise NotImplementedError

    async def safe_fetch(self, days: int) -> list[dict[str, Any]]:
        """包一层异常捕获：失败时记录日志并返回空列表，不阻断其他源。"""
        try:
            items = await self.fetch(days)
            logger.info("[%s] fetch 成功：%d 条", self.name, len(items))
            return items
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] fetch 失败：%s", self.name, exc)
            return []
