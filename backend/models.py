"""
Pydantic 模型：API 请求/响应契约 + 领域对象。

所有对外返回的新闻都必须是 NewsItem 实例，
任何 source / service 都应该产出 dict 或 NewsItem，由 aggregator 统一校验。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------
class Category(str, Enum):
    PRICE = "价格行情"
    INDUSTRY = "产业动态"
    POLICY = "政策法规"
    TRADE = "进出口贸易"


# ---------------------------------------------------------------------------
# 领域对象
# ---------------------------------------------------------------------------
class NewsItem(BaseModel):
    """单条新闻。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str
    url: str
    source: str = ""
    domain: str = ""
    published_at: datetime
    summary: Optional[str] = None
    category: Category = Category.INDUSTRY
    keywords: list[str] = Field(default_factory=list)
    credibility: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("title")
    @classmethod
    def _title_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("title 不能为空")
        return v

    @field_validator("summary", mode="before")
    @classmethod
    def _trim_summary(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = str(v).strip()
        if len(v) > 500:
            return v[:500] + "…"
        return v or None

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_category(cls, v):
        if isinstance(v, Category):
            return v
        if isinstance(v, str):
            for c in Category:
                if c.value == v or c.name == v.upper():
                    return c
        return Category.INDUSTRY


# ---------------------------------------------------------------------------
# API 响应
# ---------------------------------------------------------------------------
class NewsResponse(BaseModel):
    items: list[NewsItem]
    total: int
    last_updated: Optional[datetime] = None
    window_days: int


class RefreshResponse(BaseModel):
    status: str
    count: int
    last_updated: Optional[datetime] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    items: int
    last_updated: Optional[datetime] = None
    updating: bool
    last_error: Optional[str] = None
    window_days: int


class CategoriesResponse(BaseModel):
    categories: list[str]
