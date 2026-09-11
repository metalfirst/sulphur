"""
通用 RSS / Atom 数据源，基于 feedparser。

每个 RssSource 对应一个 feed URL（.env 中 RSS_FEEDS 逗号分隔）。
抓取用 httpx 异步完成，解析交给 feedparser（同步，很快）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from time import struct_time
from urllib.parse import urlparse

import feedparser
import httpx

from config import settings

from .base import Source, SourceError, make_item

logger = logging.getLogger("sulfur-news.sources.rss")

_USER_AGENT = "sulfur-news/0.1 (+https://example.local)"


def _struct_to_dt(st: struct_time | None) -> datetime | None:
    if not st:
        return None
    try:
        return datetime(*st[:6], tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _entry_published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        dt = _struct_to_dt(entry.get(key))
        if dt:
            return dt
    return None


def _entry_summary(entry) -> str | None:
    for key in ("summary", "description", "content"):
        v = entry.get(key)
        if not v:
            continue
        if isinstance(v, list):
            first = v[0]
            v = first.get("value") if isinstance(first, dict) else str(first)
        v = str(v).strip()
        if v:
            return v
    return None


class RssSource(Source):
    """单个 RSS / Atom 源。"""

    def __init__(self, feed_url: str, *, name: str | None = None) -> None:
        feed_url = (feed_url or "").strip()
        if not feed_url:
            raise ValueError("feed_url 不能为空")
        self.feed_url = feed_url
        self.name = name or f"rss:{urlparse(feed_url).netloc or feed_url}"

    async def fetch(self, days: int) -> list[dict]:
        headers = {"User-Agent": _USER_AGENT}

        async with httpx.AsyncClient(
            timeout=settings.fetch_timeout_seconds,
            follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(self.feed_url, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise SourceError(f"RSS 请求失败：{exc}") from exc

        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            raise SourceError(f"RSS 解析失败：{parsed.bozo_exception}")

        feed_title = (parsed.feed.get("title") or "").strip()
        domain = urlparse(self.feed_url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        items: list[dict] = []

        for entry in parsed.entries[: settings.max_items_per_source]:
            url = entry.get("link") or ""
            title = entry.get("title") or ""
            if not url or not title:
                continue

            published = _entry_published(entry)
            if published is None:
                # 没有日期的条目直接丢弃，避免"看起来最新"
                continue
            if published < cutoff:
                continue

            try:
                items.append(
                    make_item(
                        title=title,
                        url=url,
                        source=feed_title or domain,
                        domain=domain,
                        published_at=published,
                        summary=_entry_summary(entry),
                    )
                )
            except ValueError:
                continue

        return items
