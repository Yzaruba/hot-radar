/* 热品雷达 frontend — reads site/data/radar.json + trends.json (see spec §4). */
(() => {
  "use strict";

  const $ = (s) => document.querySelector(s);
  const state = { tab: "surge", cat: "all", radar: null, trends: null };
  const STATUS_KEY = "hotradar_status";
  const STATUS_NAMES = ["标记", "已定样", "已上架", "放弃"];

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
      const [radar, trends] = await Promise.all([
        fetch("data/radar.json", { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
        fetch("data/trends.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : { hashtags: [] })).catch(() => ({ hashtags: [] })),
      ]);
      state.radar = radar;
      state.trends = trends;
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
    $("#meta").innerHTML =
      `<span class="${ageH > 12 ? "old" : "fresh"}">● ${relTime(g)}更新</span><br>美区数据 · 每6小时`;
    const staleCats = state.radar.categories.filter((c) => c.stale).map((c) => c.zh);
    const warns = [];
    if (staleCats.length) warns.push(`⚠️ ${staleCats.join("/")} 品类本次抓取失败，显示上一次数据`);
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

  /* ── product cards ── */
  function visibleProducts() {
    const all = state.radar.products;
    let list;
    if (state.tab === "surge") {
      list = all.filter((p) => p.surge_rank != null).sort((a, b) => a.surge_rank - b.surge_rank);
    } else {
      list = all.filter((p) => p.list === state.tab).sort((a, b) => a.rank - b.rank);
    }
    if (state.cat !== "all") list = list.filter((p) => p.category === state.cat);
    return list;
  }

  function stickerHTML(p) {
    if (state.tab === "surge" || p.surge_rank != null) {
      if (p.is_new_entry) return `<span class="sticker new">NEW!</span>`;
      if (p.rank_pct != null) return `<span class="sticker">↑${Math.round(p.rank_pct)}%</span>`;
    }
    return `<span class="sticker">#${p.rank}</span>`;
  }

  function catZh(id) {
    const c = state.radar.categories.find((c) => c.id === id);
    return c ? c.zh : id;
  }

  function badgesHTML(p) {
    const b = [];
    if (state.cat === "all") b.push(`<span class="badge rankb">${esc(catZh(p.category))}</span>`);
    if (p.signals.tiktok && p.signals.tiktok.length)
      b.push(`<span class="badge tk" title="${esc(p.signals.tiktok.join(" #"))}">🎵 #${esc(p.signals.tiktok[0])}</span>`);
    if (p.signals.amazon_surge) b.push(`<span class="badge">📈 飙升</span>`);
    if (state.tab !== "new-releases" && p.signals.new_release) b.push(`<span class="badge rankb">🆕 新品</span>`);
    return b.length ? `<div class="badges">${b.join("")}</div>` : "";
  }

  function cardHTML(p, i) {
    const st = statuses()[p.asin] || 0;
    const rating = p.rating != null ? `<span class="rating">★${p.rating}${p.ratings_count ? ` (${Number(p.ratings_count).toLocaleString()})` : ""}</span>` : "";
    return `
<article class="card" data-i="${i}">
  <div class="card-imgwrap" data-action="view">
    ${stickerHTML(p)}
    <span class="status s${st}" data-action="status">${STATUS_NAMES[st]}</span>
    <img src="${esc(p.image)}" alt="${esc(p.title_en)}" loading="lazy">
  </div>
  <div class="card-body">
    <div class="title-zh">${esc(p.title_zh || "（未翻译）")}</div>
    <div class="title-en">${esc(p.title_en)}</div>
    ${badgesHTML(p)}
    <div class="price-row"><span class="price">${esc(p.price || "")}</span>${rating}</div>
  </div>
  <div class="card-actions">
    <a class="a1688" href="${esc(p.url_1688 || p.url_1688_fallback)}" target="_blank" rel="noopener">去1688搜</a>
    <button data-action="save" title="保存图片">💾</button>
    <button data-action="copy" title="复制英文品名">📋</button>
  </div>
</article>`;
  }

  function renderProducts() {
    const list = visibleProducts();
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
      body = `<div class="grid">${list.map((p, i) => cardHTML(p, i)).join("")}</div>`;
    }
    $("#content").innerHTML =
      `<h2 class="section-title bangers">${titles[state.tab]}</h2><p class="section-sub">${subs[state.tab]}</p>${body}`;
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
    if (p.surge_rank != null) sig.push(p.is_new_entry ? "🔥 新进榜" : `🔥 24h排名 ${p.rank_prev}→${p.rank}`);
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
    const card = actEl.closest(".card");
    if (!card) return;
    const p = state.visible[Number(card.dataset.i)];
    const action = actEl.dataset.action;
    if (action === "view") openViewer(p);
    else if (action === "save") saveImage(p);
    else if (action === "copy") copyText(p.title_en);
    else if (action === "status") {
      const next = ((statuses()[p.asin] || 0) + 1) % 4;
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
