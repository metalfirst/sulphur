"""
去重：URL 规范化 + 标题 SimHash。

策略：
  1. URL 规范化后完全相同的，只保留第一条
  2. 标题做 SimHash，与已接受条目的汉明距离 ≤ 阈值即视为重复
  3. 中英文都友好：标题归一化后用字符 3-gram 作为 shingle

输入/输出均为 list[dict]（sources 产出的标准条目）。
"""

from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config import DEDUP_HAMMING_THRESHOLD

logger = logging.getLogger("sulfur-news.services.dedup")

# ---------------------------------------------------------------------------
# URL 规范化
# ---------------------------------------------------------------------------
# 常见的追踪参数，参与去重前应当剔除
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "spm", "from", "share", "ref", "referrer", "fbclid", "gclid",
    "yclid", "mc_cid", "mc_eid", "_ga", "wt_mc",
}


def normalize_url(url: str) -> str:
    """去除 fragment、追踪参数，统一小写 scheme/host。"""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()

    scheme = parts.scheme.lower() or "http"
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # 过滤追踪参数，并按 key 排序
    qs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
          if k.lower() not in _TRACKING_PARAMS]
    qs.sort()
    query = urlencode(qs)

    # 去掉末尾多余的 /
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, query, ""))


# ---------------------------------------------------------------------------
# SimHash
# ---------------------------------------------------------------------------
_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)
_BITS = 64


def _normalize_title(title: str) -> str:
    """去除空白、标点、全角半角差异，仅保留文字与数字。"""
    t = (title or "").lower()
    t = t.replace("（", "(").replace("）", ")")
    t = _PUNCT_RE.sub("", t)
    return t


def _shingles(text: str, n: int = 3) -> list[str]:
    """字符 n-gram，中英文通用。"""
    if not text:
        return []
    if len(text) <= n:
        return [text]
    return [text[i : i + n] for i in range(len(text) - n + 1)]


def _hash64(token: str) -> int:
    """把 token 映射到 64 位整数。用 md5 保证跨进程稳定。"""
    digest = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def simhash(title: str) -> int:
    """对标题计算 64 位 SimHash。空标题返回 0。"""
    normalized = _normalize_title(title)
    shingles = _shingles(normalized)
    if not shingles:
        return 0

    v = [0] * _BITS
    for sh in shingles:
        h = _hash64(sh)
        for i in range(_BITS):
            v[i] += 1 if (h >> i) & 1 else -1

    result = 0
    for i in range(_BITS):
        if v[i] > 0:
            result |= 1 << i
    return result


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def dedup(items: list[dict]) -> list[dict]:
    """
    对原始条目去重。

    - 先按 URL 规范值去重（同 URL 只留第一条）
    - 再按 SimHash 去重（与任一已保留条目的距离 ≤ 阈值则丢弃）
    - 输入顺序即优先级顺序：靠前的条目优先保留
    """
    if not items:
        return []

    seen_urls: set[str] = set()
    kept: list[dict] = []
    kept_hashes: list[int] = []

    dropped_url = 0
    dropped_sim = 0

    for item in items:
        url_key = normalize_url(item.get("url", ""))
        if url_key and url_key in seen_urls:
            dropped_url += 1
            continue

        h = simhash(item.get("title", ""))
        if h != 0:
            duplicate = False
            for kh in kept_hashes:
                if hamming(h, kh) <= DEDUP_HAMMING_THRESHOLD:
                    duplicate = True
                    break
            if duplicate:
                dropped_sim += 1
                continue

        if url_key:
            seen_urls.add(url_key)
        kept.append(item)
        if h != 0:
            kept_hashes.append(h)

    logger.info(
        "去重完成：输入 %d 条，保留 %d 条（URL 去重 %d，SimHash 去重 %d）",
        len(items), len(kept), dropped_url, dropped_sim,
    )
    return kept
