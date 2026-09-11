# 硫磺新闻聚合（sulfur-news）

聚合近 15 天网络上与**硫磺**相关的新闻，按 **价格行情 / 产业动态 / 政策法规 / 进出口贸易** 四类展示。
不保存数据，进程重启即清空；前端通过 REST API 拉取，后端定时刷新内存缓存。

---

## 目录结构

```
sulfur-news/
├─ backend/
│  ├─ app.py                 # FastAPI 入口：路由、CORS、静态文件、启动调度
│  ├─ config.py              # 读取 .env，源/分类/可信度/缓存配置
│  ├─ models.py              # Pydantic 模型 NewsItem, Category
│  ├─ cache.py               # 内存 TTL 缓存
│  ├─ scheduler.py           # 定时刷新
│  ├─ sources/
│  │  ├─ __init__.py
│  │  ├─ base.py
│  │  ├─ gdelt.py
│  │  └─ rss.py
│  ├─ services/
│  │  ├─ aggregator.py       # 聚合、15 天过滤
│  │  ├─ dedup.py
│  │  ├─ classifier.py
│  │  └─ scorer.py
│  └─ requirements.txt
├─ frontend/
│  ├─ index.html
│  ├─ app.js
│  └─ style.css
├─ .env.example
├─ .gitignore
└─ README.md
```

---

## 快速开始

### 1. 安装依赖

```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` 建议内容：

```
fastapi>=0.110
uvicorn[standard]>=0.29
httpx>=0.27
beautifulsoup4>=4.12
lxml>=5.0
feedparser>=6.0
python-dotenv>=1.0
pydantic>=2.6
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，按需修改：

```ini
# --- 服务 ---
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
RELOAD=false
ALLOWED_ORIGINS=*

# --- 聚合 ---
NEWS_WINDOW_DAYS=15
REFRESH_INTERVAL_HOURS=4
FETCH_TIMEOUT_SECONDS=20
MAX_ITEMS_PER_SOURCE=100
REQUEST_CONCURRENCY=5

# --- GDELT ---
GDELT_API=https://api.gdeltproject.org/api/v2/doc/doc
GDELT_QUERY=(硫磺 OR sulfur OR sulphur)
GDELT_MAX_RECORDS=100
GDELT_LANGUAGE=
GDELT_SOURCE_COUNTRY=

# --- RSS（逗号分隔） ---
RSS_FEEDS=

# --- 前端（一般不用改） ---
# FRONTEND_DIR=../frontend
```

### 3. 启动

```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

访问：

- 前端页面：http://localhost:8000/
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health

---

## API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 + 缓存状态 |
| GET | `/api/categories` | 支持的分类列表 |
| GET | `/api/news` | 近 15 天新闻，支持 `category`、`q`、`limit` |
| GET | `/api/news/{category}` | 语义化分类路由 |
| POST | `/api/refresh` | 手动触发一次刷新（调试用） |

### 示例

```bash
# 全部新闻
curl http://localhost:8000/api/news

# 只看价格行情
curl "http://localhost:8000/api/news?category=价格行情"

# 搜索"港口"
curl "http://localhost:8000/api/news?q=港口&limit=20"

# 手动刷新
curl -X POST http://localhost:8000/api/refresh
```

---

## 架构说明

```
┌──────────────┐   lifespan    ┌──────────────────┐
│   FastAPI    │ ─────────────▶│  scheduler.py    │
│   app.py     │               │  refresh_news()  │
└──────┬───────┘               └────────┬─────────┘
       │ 读缓存                          │
       ▼                                 ▼
┌──────────────┐               ┌──────────────────┐
│  cache.py    │◀── commit ────│ services/        │
│  NewsCache   │               │  aggregator      │
└──────────────┘               │  dedup           │
                               │  classifier      │
                               │  scorer          │
                               └────────┬─────────┘
                                        │ fetch_all
                                        ▼
                               ┌──────────────────┐
                               │ sources/         │
                               │  gdelt / rss     │
                               └──────────────────┘
```

**关键约定**

- `sources.fetch_all(days) -> list[dict]`：返回原始条目（标题、URL、来源、时间、摘要）
- `services.aggregator.aggregate(days) -> list[NewsItem]`：
  内部完成时间过滤 → 去重 → 分类 → 关键词提取 → 可信度打分
- `cache` 只在 `scheduler` 中被写入，`app.py` 只读
- 所有对外 JSON 都由 `models.py` 中的 Pydantic 模型统一约束

---

## 配置项说明

| 变量 | 默认 | 说明 |
|------|------|------|
| `NEWS_WINDOW_DAYS` | 15 | 时间窗口（天） |
| `REFRESH_INTERVAL_HOURS` | 4 | 后台刷新间隔 |
| `ALLOWED_ORIGINS` | * | CORS 白名单，逗号分隔 |
| `GDELT_QUERY` | `(硫磺 OR sulfur OR sulphur)` | GDELT 检索式 |
| `GDELT_MAX_RECORDS` | 100 | 单次最多抓取条数 |
| `RSS_FEEDS` | 空 | RSS 源，逗号分隔 |
| `REQUEST_CONCURRENCY` | 5 | 并发抓取数 |

分类关键词、来源可信度白名单等"业务规则"在 `backend/config.py` 中以常量维护，
调整时无需改动抓取/分类代码。

---

## 扩展新数据源

1. 在 `backend/sources/` 新增一个模块（如 `smm.py`），继承 `base.Source`
2. 实现 `async def fetch(self, days: int) -> list[dict]`
3. 在 `sources/__init__.py` 的 `SOURCES` 列表里注册
4. 如需新增来源可信度，把域名加到 `config.SOURCE_CREDIBILITY`

## 扩展新分类

1. 在 `config.CATEGORY_KEYWORDS` 添加新分类及关键词
2. 在 `models.Category` 枚举中同步添加
3. `classifier.py` 会自动按新规则匹配，前端 Tab 也自动出现

---

## 设计取舍

- **不落库**：所有数据只存在内存，进程重启即清空；好处是部署零依赖
- **定时刷新 + 首次立即刷新**：前端打开就能看到数据，不需要等第一个 4 小时周期
- **刷新失败保留旧数据**：`cache.fail()` 不清空 `items`，保证接口可用性
- **静态前端可选**：`frontend/` 存在则挂载到 `/`，不存在只跑 API，方便前后端分离部署
