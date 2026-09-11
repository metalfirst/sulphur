"""
分类：基于关键词的规则匹配。

- 关键词表来自 config.CATEGORY_KEYWORDS
- 标题命中权重 2，摘要命中权重 1
- 得分最高的分类胜出；全 0 时回落到 DEFAULT_CATEGORY
- 同时返回命中的关键词列表，供前端高亮使用
"""

from __future__ import annotations

import logging

from config import CATEGORY_KEYWORDS, DEFAULT_CATEGORY

logger = logging.getLogger("sulfur-news.services.classifier")


def classify(item: dict) -> tuple[str, list[str]]:
    """
    对单条原始条目分类。

    返回 (category_name, matched_keywords)。
    category_name 是 config.CATEGORY_KEYWORDS 中的 key。
    """
    title = (item.get("title") or "").lower()
    summary = (item.get("summary") or "").lower()

    best_cat: str = DEFAULT_CATEGORY
    best_score: int = 0
    best_keywords: list[str] = []

    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        matched: list[str] = []
        for kw in keywords:
            k = kw.lower()
            in_title = k in title
            in_summary = (not in_title) and (k in summary)
            if in_title:
                score += 2
                matched.append(kw)
            elif in_summary:
                score += 1
                matched.append(kw)

        if score > best_score:
            best_score = score
            best_cat = cat
            best_keywords = matched

    # 去重并保持出现顺序
    seen: set[str] = set()
    keywords_out: list[str] = []
    for kw in best_keywords:
        if kw not in seen:
            seen.add(kw)
            keywords_out.append(kw)

    return best_cat, keywords_out


def classify_batch(items: list[dict]) -> list[dict]:
    """
    批量分类，就地写入 item['category'] 与 item['keywords']。
    返回同一列表（便于链式调用）。
    """
    for item in items:
        cat, kws = classify(item)
        item["category"] = cat
        item["keywords"] = kws
    return items
