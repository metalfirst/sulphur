/* ===========================================================================
 * sulfur-news 前端逻辑
 *
 * 职责：
 *   1. 从 /api/news 拉取数据
 *   2. 渲染新闻卡片 + 关键词高亮
 *   3. 分类 Tab 切换、搜索、手动刷新
 *   4. 自动轮询（默认 5 分钟）以反映后端缓存更新
 * =========================================================================== */

(function () {
  "use strict";

  // -------------------------------------------------------------------------
  // 配置
  // -------------------------------------------------------------------------
  const API = {
    news: "/api/news",
    health: "/api/health",
    refresh: "/api/refresh",
  };

  const POLL_INTERVAL_MS = 5 * 60 * 1000; // 前端轮询间隔
  const PAGE_LIMIT = 300;                 // 一次最多拉取条数

  // -------------------------------------------------------------------------
  // 状态
  // -------------------------------------------------------------------------
  const state = {
    category: "",
    query: "",
    items: [],
    windowDays: 15,
    lastUpdated: null,
    loading: false,
  };

  // -------------------------------------------------------------------------
  // DOM
  // -------------------------------------------------------------------------
  const el = {
    tabs: document.getElementById("tabs"),
    searchInput: document.getElementById("search-input"),
    searchClear: document.getElementById("search-clear"),
    status: document.getElementById("status"),
    list: document.getElementById("news-list"),
    empty: document.getElementById("empty-state"),
    lastUpdated: document.getElementById("last-updated"),
    refreshBtn: document.getElementById("refresh-btn"),
    windowDays: document.getElementById("window-days"),
  };

  // -------------------------------------------------------------------------
  // 工具
  // -------------------------------------------------------------------------
  const CATEGORY_CLASS = {
    "价格行情": "badge--price",
    "产业动态": "badge--industry",
    "政策法规": "badge--policy",
    "进出口贸易": "badge--trade",
  };

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /** 相对时间：几分钟前 / 几小时前 / 几天前 / 具体日期 */
  function relativeTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "";

    const diffMs = Date.now() - d.getTime();
    const diffMin = Math.round(diffMs / 60000);

    if (diffMin < 1) return "刚刚";
    if (diffMin < 60) return `${diffMin} 分钟前`;

    const diffHour = Math.round(diffMin / 60);
    if (diffHour < 24) return `${diffHour} 小时前`;

    const diffDay = Math.round(diffHour / 24);
    if (diffDay < 7) return `${diffDay} 天前`;

    return formatDate(d);
  }

  function formatDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function formatDateTime(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${formatDate(d)} ${hh}:${mm}`;
  }

  /** 对文本做关键词高亮，输入先转义再插入 <mark> */
  function highlight(text, keywords) {
    const safe = escapeHtml(text);
    if (!keywords || !keywords.length) return safe;

    // 关键词按长度倒序，避免短词切碎长词
    const kws = [...new Set(keywords)]
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);

    if (!kws.length) return safe;

    // 构造一次性的正则（转义特殊字符）
    const pattern = kws
      .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .join("|");

    try {
      const re = new RegExp(`(${pattern})`, "gi");
      return safe.replace(re, "<mark>$1</mark>");
    } catch {
      return safe;
    }
  }

  // -------------------------------------------------------------------------
  // 渲染
  // -------------------------------------------------------------------------
  function setStatus(message, type) {
    if (!message) {
      el.status.hidden = true;
      el.status.textContent = "";
      el.status.classList.remove("error");
      return;
    }
    el.status.hidden = false;
    el.status.textContent = message;
    el.status.classList.toggle("error", type === "error");
  }

  function renderSkeleton(count = 5) {
    const frag = document.createDocumentFragment();
    for (let i = 0; i < count; i++) {
      const div = document.createElement("div");
      div.className = "skeleton";
      div.innerHTML =
        '<div class="skeleton__line skeleton__line--short"></div>' +
        '<div class="skeleton__line skeleton__line--long"></div>' +
        '<div class="skeleton__line"></div>';
      frag.appendChild(div);
    }
    el.list.innerHTML = "";
    el.list.appendChild(frag);
    el.empty.hidden = true;
  }

  function renderCards(items) {
    el.list.innerHTML = "";

    if (!items.length) {
      el.empty.hidden = false;
      return;
    }
    el.empty.hidden = true;

    const frag = document.createDocumentFragment();

    for (const item of items) {
      const card = document.createElement("article");
      card.className = "news-card";

      const catClass = CATEGORY_CLASS[item.category] || "badge--industry";
      const source = escapeHtml(item.source || item.domain || "");
      const timeText = relativeTime(item.published_at);
      const timeTitle = formatDateTime(item.published_at);

      const titleHtml = highlight(item.title, item.keywords);
      const summaryHtml = item.summary
        ? highlight(item.summary, item.keywords)
        : "";

      const keywordsHtml =
        item.keywords && item.keywords.length
          ? `<div class="news-card__keywords">${item.keywords
              .slice(0, 6)
              .map((k) => `<span class="keyword">${escapeHtml(k)}</span>`)
              .join("")}</div>`
          : "";

      card.innerHTML = `
        <div class="news-card__top">
          <span class="badge ${catClass}">${escapeHtml(item.category)}</span>
          ${source ? `<span class="news-card__source">${source}</span>` : ""}
          <span class="news-card__time" title="${timeTitle}">${timeText}</span>
        </div>
        <h2 class="news-card__title">
          <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">
            ${titleHtml}
          </a>
        </h2>
        ${summaryHtml ? `<p class="news-card__summary">${summaryHtml}</p>` : ""}
        ${keywordsHtml}
      `;

      frag.appendChild(card);
    }

    el.list.appendChild(frag);
  }

  function renderMeta() {
    if (state.lastUpdated) {
      el.lastUpdated.textContent = `更新于 ${formatDateTime(state.lastUpdated)}`;
    } else {
      el.lastUpdated.textContent = "尚未更新";
    }
    el.windowDays.textContent = String(state.windowDays);
  }

  // -------------------------------------------------------------------------
  // 数据请求
  // -------------------------------------------------------------------------
  async function fetchNews() {
    const params = new URLSearchParams();
    if (state.category) params.set("category", state.category);
    if (state.query) params.set("q", state.query);
    params.set("limit", String(PAGE_LIMIT));

    const res = await fetch(`${API.news}?${params.toString()}`);
    if (!res.ok) {
      throw new Error(`请求失败：${res.status}`);
    }
    return res.json();
  }

  async function load(options = {}) {
    const { showSkeleton = false } = options;
    if (state.loading) return;
    state.loading = true;

    if (showSkeleton) renderSkeleton();
    setStatus("");

    try {
      const data = await fetchNews();
      state.items = data.items || [];
      state.windowDays = data.window_days || state.windowDays;
      state.lastUpdated = data.last_updated || null;
      renderCards(state.items);
      renderMeta();
    } catch (err) {
      console.error(err);
      setStatus(`加载失败：${err.message}`, "error");
      el.list.innerHTML = "";
      el.empty.hidden = false;
    } finally {
      state.loading = false;
    }
  }

  async function manualRefresh() {
    if (el.refreshBtn.disabled) return;
    el.refreshBtn.disabled = true;
    el.refreshBtn.classList.add("loading");
    setStatus("正在刷新数据源，请稍候…");

    try {
      const res = await fetch(API.refresh, { method: "POST" });
      if (res.status === 429) {
        setStatus("已有刷新任务进行中，请稍后再试");
      } else if (!res.ok) {
        throw new Error(`刷新失败：${res.status}`);
      } else {
        const data = await res.json();
        if (data.status === "ok") {
          setStatus(`刷新完成，共 ${data.count} 条`);
        } else {
          setStatus(`刷新异常：${data.error || "未知错误"}`, "error");
        }
      }
      await load();
    } catch (err) {
      console.error(err);
      setStatus(`刷新失败：${err.message}`, "error");
    } finally {
      el.refreshBtn.disabled = false;
      el.refreshBtn.classList.remove("loading");
      // 3 秒后自动清除提示
      setTimeout(() => setStatus(""), 3000);
    }
  }

  // -------------------------------------------------------------------------
  // 事件绑定
  // -------------------------------------------------------------------------
  function bindTabs() {
    el.tabs.addEventListener("click", (e) => {
      const btn = e.target.closest(".tab");
      if (!btn) return;
      const cat = btn.dataset.category || "";
      if (cat === state.category) return;

      state.category = cat;
      el.tabs.querySelectorAll(".tab").forEach((t) =>
        t.classList.toggle("active", t === btn)
      );
      load({ showSkeleton: true });
    });
  }

  function bindSearch() {
    let timer = null;

    const apply = () => {
      const v = el.searchInput.value.trim();
      el.searchClear.hidden = !v;
      if (v === state.query) return;
      state.query = v;
      load({ showSkeleton: true });
    };

    el.searchInput.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(apply, 300); // 防抖
    });

    el.searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        clearTimeout(timer);
        apply();
      }
    });

    el.searchClear.addEventListener("click", () => {
      el.searchInput.value = "";
      el.searchClear.hidden = true;
      if (state.query) {
        state.query = "";
        load({ showSkeleton: true });
      }
      el.searchInput.focus();
    });
  }

  function bindRefresh() {
    el.refreshBtn.addEventListener("click", manualRefresh);
  }

  function startPolling() {
    setInterval(() => {
      // 页面隐藏时不刷新，节省资源
      if (document.hidden) return;
      load();
    }, POLL_INTERVAL_MS);
  }

  // -------------------------------------------------------------------------
  // 启动
  // -------------------------------------------------------------------------
  function init() {
    bindTabs();
    bindSearch();
    bindRefresh();
    load({ showSkeleton: true });
    startPolling();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
