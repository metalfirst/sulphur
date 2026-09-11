"""
进程内新闻缓存：不落库，重启即清空。

设计要点：
  - 使用 RLock 保护多线程/协程并发访问
  - try_begin_update / commit / fail 三态，保证同一时刻只有一次刷新
  - items 返回副本，避免调用方意外修改内部列表
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from models import NewsItem


class NewsCache:
    """线程安全的内存缓存。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: list[NewsItem] = []
        self._last_updated: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._updating: bool = False

    # -------- 只读访问 --------
    @property
    def items(self) -> list[NewsItem]:
        with self._lock:
            return list(self._items)

    @property
    def last_updated(self) -> Optional[datetime]:
        with self._lock:
            return self._last_updated

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    @property
    def updating(self) -> bool:
        with self._lock:
            return self._updating

    def is_empty(self) -> bool:
        with self._lock:
            return not self._items

    # -------- 刷新三态 --------
    def try_begin_update(self) -> bool:
        """尝试进入刷新状态。已在刷新中则返回 False。"""
        with self._lock:
            if self._updating:
                return False
            self._updating = True
            return True

    def commit(self, items: list[NewsItem]) -> None:
        """刷新成功，覆盖缓存并记录时间。"""
        with self._lock:
            self._items = list(items)
            self._last_updated = datetime.now(timezone.utc)
            self._last_error = None
            self._updating = False

    def fail(self, error: str) -> None:
        """刷新失败，保留旧数据，只记录错误。"""
        with self._lock:
            self._last_error = error
            self._updating = False

    # -------- 工具 --------
    def reset(self) -> None:
        with self._lock:
            self._items = []
            self._last_updated = None
            self._last_error = None
            self._updating = False

    def stats(self) -> dict:
        with self._lock:
            return {
                "items": len(self._items),
                "last_updated": self._last_updated,
                "last_error": self._last_error,
                "updating": self._updating,
            }


# 全局单例
cache = NewsCache()
