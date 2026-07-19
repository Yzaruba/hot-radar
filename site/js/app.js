/* 热品雷达 frontend — reads site/data/radar.json + trends.json (see spec §4). */
(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const state = { tab: "surge", cat: "all", radar: null, trends: null, runMeta: null };
  const LIST_ZH = { bestsellers: "畅销", "new-releases": "新品" };
  const STATUS_KEY = "hotradar_status";
  // indices 1-3 are long-standing stored values — only ever APPEND here
  const STATUS_NAMES = ["标记", "已定样", "已上架", "放弃", "观察中"];
  const RECO_CLASS = { "立即找货": "r1", "小批测试": "r2", "继续观察": "r3", "高风险": "r4" };
  const CONF_ZH = { high: "置信度高", medium: "置信度中", low: "置信度低" };

  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const statuses = () => {
    try { return JSON.parse(localStorage.getItem(STATUS_KEY)) || {}; } catch { return {}; }
  };
  const setStatus = (asin, v) => {
    const all = statuses();
    if (v) all[asin] = v; else delete all[asin];
    localStorage.setItem(STATUS_KEY, JSON.stringify(all));
  };

  let toastTimer;
  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 2600);
  }

  function relTime(iso) {
    const mins = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
    if (mins < 60) return `${mins}分钟前`;
    if (mins < 48 * 60) return `${Math.round(mins / 60)}小时前`;
    return `${Math.round(mins / 1440)}天前`;
  }

  /* ── data loading ── */
  async function loadData() {
    try {
      const [radar, trends, runMeta] = await Promise.all([
        fetch("data/radar.json", { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
        fetch("data/trends.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : { hashtags: [] })).catch(() => ({ hashtags: [] })),
        fetch("data/run_meta.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ]);
      state.radar = radar;
      state.trends = trends;
      state.runMeta = runMeta;
      renderMeta();
      $("#chips").hidden = false;
      renderChips();
      render();
    } catch (e) {
      $("#content").innerHTML =
        `<div class="empty"><span class="big">OOPS!</span>数据加载失败（${esc(e.message)}）<br>` +
        `<button class="retry-btn" id="retry">重试</button></div>`;
      $("#retry").onclick = loadData;
    }
  }

  function renderMeta() {
    const g = state.radar.generated_at;
    const ageH = (Date.now() - Date.parse(g)) / 3600000;
    const abs = new Date(g).toLocaleString("zh-CN", {
      month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
    });
    const rm = state.runMeta;
    const totalPairs = state.radar.categories.length * 2;
    const cover = rm && rm.fresh_pairs ? ` · 覆盖${rm.fresh_pairs.length}/${totalPairs}榜单` : "";
    const incomplete =
      (rm && rm.stale_pairs && rm.stale_pairs.length > 0) ||
      state.radar.categories.some((c) => c.stale);
    const t3 = state.radar.top3;
    const actions = t3 && t3.asins ? t3.asins.length : 0;
    $("#meta").innerHTML =
      `<span class="${ageH > 12 ? "old" : "fresh"}">● ${relTime(g)}更新</span><br>${abs}${cover}<br>` +
      `${incomplete ? "⚠️数据不完整" : "数据完整"} · 今日${actions}个行动`;
    const warns = [];
    if (ageH > 12) warns.push(`⚠️ 数据已 ${Math.round(ageH)} 小时未更新`);
    if (rm && rm.stale_pairs && rm.stale_pairs.length) {
      const names = rm.stale_pairs.map((s) => {
        const [k, c] = s.split(":");
        return `${LIST_ZH[k] || k}/${catZh(c)}`;
      });
      warns.push(`⚠️ 本次抓取失败(沿用旧数据)：${names.join("、")}`);
    } else {
      const staleCats = state.radar.categories.filter((c) => c.stale).map((c) => c.zh);
      if (staleCats.length) warns.push(`⚠️ ${staleCats.join("/")} 品类本次抓取失败，显示上一次数据`);
    }
    if (state.trends && state.trends.stale) warns.push("⚠️ TikTok 数据为上次缓存");
    if (state.radar.real_movers_available) warns.push("🎉 Amazon 官方飙升榜恢复可用了，可通知开发升级");
    const bar = $("#warnbar");
    bar.hidden = warns.length === 0;
    bar.textContent = warns.join("　");
  }

  /* ── chips ── */
  function renderChips() {
    const el = $("#chips");
    if (state.tab === "tiktok") { el.hidden = true; return; }
    el.hidden = false;
    const cats = [{ id: "all", zh: "全部" }, ...state.radar.categories];
    el.innerHTML = cats
      .map((c) => `<button class="chip ${state.cat === c.id ? "active" : ""}" data-cat="${c.id}">${esc(c.zh)}</button>`)
      .join("");
  }

  /* ── product cards (schema v2: one product per ASIN, placements in sources[]) ── */
  function viewsFor() {
    const all = state.radar.products;
    if (state.tab === "surge") {
      return all
        .filter((p) => p.surge_rank != null && p.surge)
        .filter((p) => state.cat === "all" || p.surge.category === state.cat)
        .sort((a, b) => a.surge_rank - b.surge_rank)
        .map((p) => ({ p, rank: p.surge.rank, category: p.surge.category }));
    }
    const views = [];
    for (const p of all) {
      let srcs = (p.sources || []).filter((s) => s.list === state.tab);
      if (state.cat !== "all") srcs = srcs.filter((s) => s.category === state.cat);
      if (!srcs.length) continue;
      const best = srcs.reduce((a, b) => (a.rank <= b.rank ? a : b));
      views.push({ p, rank: best.rank, category: best.category });
    }
    views.sort((a, b) => a.rank - b.rank);
    return views;
  }

  function stickerHTML(v) {
    if (state.tab === "surge") {
      if (v.p.surge.is_new_entry) return `<span class="sticker new">NEW!</span>`;
      if (v.p.surge.rank_pct != null) return `<span class="sticker">↑${Math.round(v.p.surge.rank_pct)}%</span>`;
    }
    return `<span class="sticker">#${v.rank}</span>`;
  }

  function catZh(id) {
    const c = state.radar.categories.find((c) => c.id === id);
    return c ? c.zh : id;
  }

  function badgesHTML(v) {
    const p = v.p;
    const b = [];
    if (state.cat === "all") b.push(`<span class="badge rankb">${esc(catZh(v.category))}</span>`);
    if (p.signals.tiktok && p.signals.tiktok.length)
      b.push(`<span class="badge tk" title="${esc(p.signals.tiktok.join(" #"))}">🎵 #${esc(p.signals.tiktok[0])}</span>`);
    if (state.tab !== "surge" && p.signals.amazon_surge) b.push(`<span class="badge">📈 飙升</span>`);
    if (state.tab !== "new-releases" && p.signals.new_release) b.push(`<span class="badge rankb">🆕 新品</span>`);
    return b.length ? `<div class="badges">${b.join("")}</div>` : "";
  }

  function cardHTML(v, i) {
    const p = v.p;
    const st = statuses()[p.asin] || 0;
    const rating = p.rating != null ? `<span class="rating">★${p.rating}${p.ratings_count ? ` (${Number(p.ratings_count).toLocaleString()})` : ""}</span>` : "";
    return `
<article class="card" data-i="${i}">
  <div class="card-imgwrap" data-action="view">
    ${stickerHTML(v)}
    <span class="status s${st}" data-action="status">${STATUS_NAMES[st]}</span>
    <img src="${esc(p.image)}" alt="${esc(p.title_en)}" loading="lazy">
  </div>
  <div class="card-body">
    <div class="title-zh">${esc(p.title_zh || "（未翻译）")}</div>
    <div class="title-en">${esc(p.title_en)}</div>
    ${badgesHTML(v)}
    <div class="price-row"><span class="price">${esc(p.price || "")}</span>${rating}</div>
  </div>
  <div class="card-actions">
    <a class="a1688" href="${esc(p.url_1688 || p.url_1688_fallback)}" target="_blank" rel="noopener">去1688搜</a>
    <button data-action="save" title="保存图片">💾</button>
    <button data-action="copy" title="复制英文品名">📋</button>
  </div>
</article>`;
  }

  /* ── today's top 3 hero (first screen, surge tab only) ── */
  function renderTop3HTML() {
    const t3 = state.radar.top3;
    const header = `<h2 class="section-title bangers">⚡ 今日 Top 3</h2>`;
    if (!t3 || !t3.asins || !t3.asins.length) {
      state.top3 = [];
      return `<section class="top3">${header}
        <div class="empty"><span class="big">NONE</span>今天没有商品达到推荐标准<br>去下面的榜单自己淘一淘</div></section>`;
    }
    const byAsin = new Map(state.radar.products.map((p) => [p.asin, p]));
    state.top3 = t3.asins.map((a) => byAsin.get(a)).filter(Boolean);
    const note =
      t3.qualified_count < 3
        ? `<p class="top3-note">⚠️ 今天只有 ${t3.qualified_count} 个商品达到推荐标准，宁缺毋滥</p>`
        : `<p class="top3-note">${t3.qualified_count} 个商品达标 · 展示最强 3 个</p>`;
    const cards = state.top3
      .map((p, i) => {
        const st = statuses()[p.asin] || 0;
        const watching = st === 4;
        return `
<article class="hero" data-t3="${i}">
  <span class="hero-rank bangers">TOP ${i + 1}</span>
  <div class="hero-img" data-action="t3view"><img src="${esc(p.image)}" alt="${esc(p.title_en)}"></div>
  <div class="hero-body">
    <div class="hero-score">
      <span class="bangers hs-num">${Math.round(p.opportunity_score)}</span>
      <span class="conf conf-${p.confidence}">${CONF_ZH[p.confidence] || ""}</span>
      <span class="reco ${RECO_CLASS[p.recommendation] || "r3"}">${esc(p.recommendation)}</span>
    </div>
    <div class="hero-name">${esc(p.keyword_zh || p.title_zh || p.title_en)}</div>
    <div class="hero-why">✅ ${esc(p.reason_zh || "")}</div>
    <div class="hero-risk">⚠️ ${esc(p.primary_risk_zh || "")}</div>
    <div class="hero-actions">
      <button data-action="t3view">查看详情</button>
      <a class="h1688" href="${esc(p.url_1688 || p.url_1688_fallback)}" target="_blank" rel="noopener">去1688搜</a>
      <button data-action="t3watch" class="${watching ? "on" : ""}">${watching ? "👁 观察中" : "标记观察"}</button>
    </div>
  </div>
</article>`;
      })
      .join("");
    return `<section class="top3">${header}${note}<div class="top3-cards">${cards}</div></section>`;
  }

  function renderProducts() {
    const list = viewsFor();
    const titles = { surge: "🔥 飙升榜", bestsellers: "📈 畅销榜", "new-releases": "🆕 新品榜" };
    const subs = {
      surge: "对比24小时前排名自动计算 · 涨得猛的才配上榜",
      bestsellers: "Amazon 美区各品类 Top 100",
      "new-releases": "Amazon 美区新品榜 · 工厂端的先行信号",
    };
    let body;
    const surgeEmptyGlobally =
      state.tab === "surge" && !state.radar.products.some((p) => p.surge_rank != null);
    if (surgeEmptyGlobally) {
      body = `<div class="empty"><span class="big">CHARGING…</span>飙升榜需要积累两次抓取（约24小时）后出现<br>先去畅销榜和新品榜逛逛</div>`;
    } else if (!list.length) {
      body = `<div class="empty"><span class="big">EMPTY!</span>这个品类暂时没有上榜商品</div>`;
    } else {
      body = `<div class="grid">${list.map((v, i) => cardHTML(v, i)).join("")}</div>`;
    }
    const top3Html = state.tab === "surge" ? renderTop3HTML() : "";
    $("#content").innerHTML =
      `${top3Html}<h2 class="section-title bangers">${titles[state.tab]}</h2><p class="section-sub">${subs[state.tab]}</p>${body}`;
    state.visible = list;
  }

  /* ── tiktok trends ── */
  function sparkline(curve) {
    if (!curve || curve.length < 2) return "";
    const w = 72, h = 28, max = Math.max(...curve, 1);
    const pts = curve.map((v, i) => `${(i / (curve.length - 1)) * w},${h - (v / max) * (h - 4) - 2}`).join(" ");
    return `<svg class="trend-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
      <polyline points="${pts}" fill="none" stroke="#e60023" stroke-width="2.5"/></svg>`;
  }

  function renderTrends() {
    const tags = (state.trends && state.trends.hashtags) || [];
    const rows = tags
      .map((t) => `
<div class="trend">
  <div class="trend-rank bangers">${t.rank}</div>
  <div class="trend-main">
    <div class="trend-tag">#${esc(t.name)}</div>
    <div class="trend-zh">${esc(t.zh || "")}</div>
    <div class="trend-posts">${Number(t.posts).toLocaleString()} 帖 · 7日热度</div>
  </div>
  ${sparkline(t.curve)}
  <div class="trend-actions">${t.url_1688 ? `<a href="${esc(t.url_1688)}" target="_blank" rel="noopener">1688</a>` : ""}</div>
</div>`)
      .join("");
    $("#content").innerHTML =
      `<h2 class="section-title bangers">🎵 TikTok 热标签</h2>
       <p class="section-sub">美区7日趋势 · 官方创意中心 · 命中的商品卡会亮 🎵 标</p>` +
      (rows || `<div class="empty"><span class="big">EMPTY!</span>暂无标签数据</div>`);
  }

  function render() {
    renderChips();
    if (state.tab === "tiktok") renderTrends();
    else renderProducts();
    window.scrollTo(0, 0);
  }

  /* ── save image / share ── */
  async function fetchBlob(p) {
    const r = await fetch(p.image);
    if (!r.ok) throw new Error("image fetch failed");
    return r.blob();
  }

  async function saveImage(p, blobPromise) {
    try {
      let blob = blobPromise ? await blobPromise : null;
      if (!blob) blob = await fetchBlob(p); // prefetch failed or absent — retry live
      if (!blob.size) throw new Error("empty image");
      const file = new File([blob], `${p.asin}.jpg`, { type: blob.type || "image/jpeg" });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        try {
          await navigator.share({ files: [file] });
          return;
        } catch (err) {
          if (err && err.name === "AbortError") return; // user closed the sheet
        }
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${p.asin}.jpg`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast("已下载图片 📥");
    } catch {
      toast("保存失败，试试长按图片保存");
    }
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast("已复制英文品名 📋");
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
      toast("已复制英文品名 📋");
    }
  }

  /* ── fullscreen viewer ── */
  let viewerProduct = null;
  let viewerBlob = null;

  function openViewer(p) {
    viewerProduct = p;
    viewerBlob = fetchBlob(p).catch(() => null); // prefetch so save happens within tap gesture
    $("#viewerImg").src = p.image;
    const sig = [];
    if (p.signals.tiktok && p.signals.tiktok.length) sig.push(`🎵 TikTok热标签：#${p.signals.tiktok.join(" #")}`);
    if (p.surge) sig.push(p.surge.is_new_entry ? "🔥 新进榜" : `🔥 24h排名 ${p.surge.rank_prev}→${p.surge.rank}`);
    $("#viewerInfo").innerHTML =
      `<div class="vi-zh">${esc(p.title_zh || "")}</div>
       <div class="vi-en">${esc(p.title_en)}</div>
       ${sig.length ? `<div class="vi-sig">${esc(sig.join("　"))}</div>` : ""}`;
    $("#btn1688").href = p.url_1688 || p.url_1688_fallback;
    $("#btnAmazon").href = p.amazon_url;
    $("#viewer").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeViewer() {
    $("#viewer").hidden = true;
    $("#viewerImg").src = "";
    document.body.style.overflow = "";
    viewerProduct = null;
    viewerBlob = null;
  }

  /* ── events ── */
  $("#tabbar").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-tab]");
    if (!btn) return;
    state.tab = btn.dataset.tab;
    document.querySelectorAll("#tabbar button").forEach((b) => b.classList.toggle("active", b === btn));
    render();
  });

  $("#chips").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    state.cat = chip.dataset.cat;
    render();
  });

  $("#content").addEventListener("click", (e) => {
    const actEl = e.target.closest("[data-action]");
    if (!actEl) return;
    const hero = actEl.closest(".hero");
    if (hero) {
      const p = (state.top3 || [])[Number(hero.dataset.t3)];
      if (!p) return;
      const action = actEl.dataset.action;
      if (action === "t3view") openViewer(p);
      else if (action === "t3watch") {
        const st = statuses()[p.asin] || 0;
        if (st >= 1 && st <= 3) {
          toast(`已有标记：${STATUS_NAMES[st]}`);
          return;
        }
        const next = st === 4 ? 0 : 4;
        setStatus(p.asin, next);
        actEl.classList.toggle("on", next === 4);
        actEl.textContent = next === 4 ? "👁 观察中" : "标记观察";
        toast(next === 4 ? "已加入观察清单 👁" : "已取消观察");
      }
      return;
    }
    const card = actEl.closest(".card");
    if (!card) return;
    const view = state.visible[Number(card.dataset.i)];
    if (!view) return;
    const p = view.p;
    const action = actEl.dataset.action;
    if (action === "view") openViewer(p);
    else if (action === "save") saveImage(p);
    else if (action === "copy") copyText(p.title_en);
    else if (action === "status") {
      const next = ((statuses()[p.asin] || 0) + 1) % STATUS_NAMES.length;
      setStatus(p.asin, next);
      actEl.className = `status s${next}`;
      actEl.textContent = STATUS_NAMES[next];
      if (next) toast(`已标记：${STATUS_NAMES[next]}`);
    }
  });

  $("#viewerClose").addEventListener("click", closeViewer);
  $("#btnSave").addEventListener("click", () => viewerProduct && saveImage(viewerProduct, viewerBlob));
  $("#btnCopy").addEventListener("click", () => viewerProduct && copyText(viewerProduct.title_en));

  // chips stick right below the topbar, whose height varies with safe-area insets
  const setTopbarH = () => {
    const tb = document.querySelector(".topbar");
    if (tb) document.documentElement.style.setProperty("--topbar-h", `${tb.offsetHeight}px`);
  };
  setTopbarH();
  window.addEventListener("resize", setTopbarH);

  // keep the freshness indicator honest on a tab left open
  setInterval(() => {
    if (state.radar) renderMeta();
  }, 60000);

  loadData();
})();
