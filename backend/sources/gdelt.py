"""
GDELT DOC 2.0 API 数据源。

接口文档：https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
返回 JSON 结构：
    {"articles": [
        {"url": ..., "title": ..., "seendate": "20260910T123000Z",
         "domain": ..., "language": ..., "sourcecountry": ...},
        ...
    ]}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx

from config import settings

from .base import Source, SourceError, make_item

logger = logging.getLogger("sulfur-news.sources.gdelt")

_USER_AGENT = "sulfur-news/0.1 (+https://example.local)"


def _parse_seendate(s: str | None) -> datetime | None:
    """GDELT 的 seendate 形如 20260910T123000Z。"""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _extract_domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:  # noqa: BLE001
        return ""


class GdeltSource(Source):
    """通过 GDELT Doc API 检索多语种新闻。"""

    name = "gdelt"

    async def fetch(self, days: int) -> list[dict]:
        if not settings.gdelt_api:
            return []

        # 组装查询式：基础式 + 可选语言/国家过滤
        query = settings.gdelt_query or "(硫磺 OR sulfur OR sulphur)"
        if settings.gdelt_language:
            query = f"{query} sourcelang:{settings.gdelt_language}"
        if settings.gdelt_source_country:
            query = f"{query} sourcecountry:{settings.gdelt_source_country}"

        params = {
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(settings.gdelt_max_records),
            "timespan": f"{days}d",
            "sort": "DateDesc",
        }
        headers = {"User-Agent": _USER_AGENT}

        async with httpx.AsyncClient(timeout=settings.fetch_timeout_seconds) as client:
            try:
                resp = await client.get(settings.gdelt_api, params=params, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise SourceError(f"GDELT 请求失败：{exc}") from exc

            # GDELT 有时把 JSON 以 text/plain 返回，优先尝试 resp.json()
            try:
                data = resp.json()
            except ValueError:
                text = (resp.text or "").strip()
                if not text:
                    return []
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise SourceError(f"GDELT 返回非 JSON：{text[:200]}") from exc

        articles = data.get("articles") or []
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        items: list[dict] = []
        for art in articles:
            url = art.get("url") or ""
            title = art.get("title") or ""
            if not url or not title:
                continue

            published = _parse_seendate(art.get("seendate"))
            if published is None:
                # 无日期的条目：保守起见丢弃，避免下游按当前时间误判"最新"
                continue
            if published < cutoff:
                continue

            domain = (art.get("domain") or _extract_domain(url)).lower()

            try:
                items.append(
                    make_item(
                        title=title,
                        url=url,
                        source=domain,
                        domain=domain,
                        published_at=published,
                        summary=None,
                    )
                )
            except ValueError:
                continue

        return items
