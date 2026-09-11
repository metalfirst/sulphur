"""
配置中心：环境变量 + 静态规则表。

约定：
  - 所有可变配置从 .env 读取，进程启动时解析一次
  - 分类关键词、可信度白名单等"业务规则"以常量形式放在这里
  - sources/ 和 services/ 通过 `from config import ...` 使用
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（backend/ 的上一级）
ROOT_DIR = Path(__file__).resolve().parent.parent

# 优先加载项目根 .env；不存在则忽略
load_dotenv(ROOT_DIR / ".env")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(key: str, default: list[str] | None = None, sep: str = ",") -> list[str]:
    v = os.getenv(key)
    if not v:
        return list(default or [])
    return [x.strip() for x in v.split(sep) if x.strip()]


# ---------------------------------------------------------------------------
# 运行期配置
# ---------------------------------------------------------------------------
class _Settings:
    """进程级配置，构造时解析环境变量。"""

    def __init__(self) -> None:
        # --- 服务 ---
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.reload: bool = _env_bool("RELOAD", False)
        self.allowed_origins: list[str] = _env_list("ALLOWED_ORIGINS", ["*"])

        # --- 聚合 ---
        self.news_window_days: int = int(os.getenv("NEWS_WINDOW_DAYS", "15"))
        self.refresh_interval_hours: float = float(
            os.getenv("REFRESH_INTERVAL_HOURS", "4")
        )
        self.fetch_timeout_seconds: float = float(
            os.getenv("FETCH_TIMEOUT_SECONDS", "20")
        )
        self.max_items_per_source: int = int(
            os.getenv("MAX_ITEMS_PER_SOURCE", "100")
        )
        self.request_concurrency: int = int(os.getenv("REQUEST_CONCURRENCY", "5"))

        # --- GDELT ---
        self.gdelt_api: str = os.getenv(
            "GDELT_API", "https://api.gdeltproject.org/api/v2/doc/doc"
        )
        self.gdelt_query: str = os.getenv(
            "GDELT_QUERY",
            "(硫磺 OR sulfur OR sulphur)",
        )
        self.gdelt_max_records: int = int(os.getenv("GDELT_MAX_RECORDS", "100"))
        self.gdelt_language: str = os.getenv("GDELT_LANGUAGE", "")  # 空=不限
        self.gdelt_source_country: str = os.getenv("GDELT_SOURCE_COUNTRY", "")

        # --- RSS ---
        self.rss_feeds: list[str] = _env_list("RSS_FEEDS", [])

        # --- 前端 ---
        self.frontend_dir: Path = Path(
            os.getenv("FRONTEND_DIR", str(ROOT_DIR / "frontend"))
        ).resolve()


settings = _Settings()


# ---------------------------------------------------------------------------
# 分类关键词（用于 services/classifier.py）
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "价格行情": [
        "价格", "报价", "行情", "成交价", "涨", "跌", "调价",
        "CFR", "FOB", "美元/吨", "元/吨", "竞拍",
        "price", "quotation", "market",
    ],
    "产业动态": [
        "项目", "投产", "建设", "产能", "装置", "开工", "扩产",
        "技改", "签约", "并购", "开工率",
        "plant", "project", "capacity", "production", "expansion",
    ],
    "政策法规": [
        "通知", "政策", "监管", "安全", "整治", "规定", "条例",
        "办法", "标准", "执法", "环保", "环评",
        "policy", "regulation", "notice", "safety", "compliance",
    ],
    "进出口贸易": [
        "进口", "出口", "海关", "到港", "禁令", "关税", "贸易",
        "采购", "合同", "船期", "库存", "发运",
        "import", "export", "customs", "tariff", "shipment", "inventory",
    ],
}

# 默认分类（关键词全不命中时使用）
DEFAULT_CATEGORY: str = "产业动态"

# 高亮关键词（前端可用，classifier 也用它标记 matched_keywords）
HIGHLIGHT_KEYWORDS: list[str] = sorted(
    {kw.lower() for kws in CATEGORY_KEYWORDS.values() for kw in kws}
)


# ---------------------------------------------------------------------------
# 来源可信度（用于 services/scorer.py）
# ---------------------------------------------------------------------------
# 匹配方式：域名子串包含（不区分大小写）
SOURCE_CREDIBILITY: dict[str, float] = {
    # 官方 / 政府
    "ndrc.gov.cn": 1.0,
    "mofcom.gov.cn": 1.0,
    "customs.gov.cn": 0.95,
    "stats.gov.cn": 0.95,
    "gov.cn": 0.95,
    # 行业媒体
    "ccin.com.cn": 0.9,        # 中化新网
    "sinopecnews.com.cn": 0.9,
    "chemnet.com": 0.85,       # 生意社
    "mysteel.com": 0.85,       # 我的钢铁
    "oilchem.net": 0.85,       # 隆众资讯
    "smm.cn": 0.85,            # 上海有色网
    "cnfeol.com": 0.8,
    # 主流通讯社 / 财经
    "reuters.com": 0.9,
    "bloomberg.com": 0.9,
    "xinhuanet.com": 0.9,
    "people.com.cn": 0.9,
    "chinanews.com.cn": 0.85,
    "finance.sina.com.cn": 0.7,
    "eastmoney.com": 0.7,
}

# 未命中白名单时的默认可信度
DEFAULT_CREDIBILITY: float = 0.5


# ---------------------------------------------------------------------------
# 去重 / 时效
# ---------------------------------------------------------------------------
# 标题 SimHash 汉明距离阈值（越小越严格）
DEDUP_HAMMING_THRESHOLD: int = 6

# 同一域名同一标题的重复判定窗口（秒）
DEDUP_NEAR_DUPLICATE_WINDOW_SECONDS: int = 3600 * 24
