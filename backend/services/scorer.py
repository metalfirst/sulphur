"""
可信度评分。

规则：
  - 用 item 的 domain / source 去匹配 config.SOURCE_CREDIBILITY
  - 采用"最长匹配优先"：命中最长的域名决定得分，避免误命中
  - 未命中任何白名单则回落到 DEFAULT_CREDIBILITY
"""

from __future__ import annotations

import logging

from config import DEFAULT_CREDIBILITY, SOURCE_CREDIBILITY

logger = logging.getLogger("sulfur-news.services.scorer")


def score_item(item: dict) -> float:
    """返回 [0, 1] 之间的可信度分数。"""
    domain = (item.get("domain") or "").lower()
    source = (item.get("source") or "").lower()
    haystack = f"{domain} {source}"

    best: float | None = None
    best_len = 0

    for pattern, cred in SOURCE_CREDIBILITY.items():
        p = pattern.lower()
        if p and p in haystack and len(p) > best_len:
            best = cred
            best_len = len(p)

    return best if best is not None else DEFAULT_CREDIBILITY


def score_batch(items: list[dict]) -> list[dict]:
    """批量打分，就地写入 item['credibility']。"""
    for item in items:
        item["credibility"] = score_item(item)
    return items
