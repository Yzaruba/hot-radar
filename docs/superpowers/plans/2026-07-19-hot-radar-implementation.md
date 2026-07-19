# 热品雷达 Hot Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 零成本自动化热品雷达：GitHub Actions 每6小时抓 Amazon 榜单+TikTok 热标签 → 自算飙升榜 → manga红黑风静态页 → GitHub Pages 手机访问。

**Architecture:** Python 抓取管线（Playwright 抓 Amazon zg 榜单、httpx 调 TikTok KnowledgeAPI、快照对比自算 movers、gtx 翻译带缓存、商品图镜像同源化）产出两个 JSON 契约文件；纯静态前端 fetch 渲染；单 workflow 两 job（scrape+commit → deploy-pages，Pages 源=GitHub Actions）。

**Tech Stack:** Python 3.11, playwright(chromium), httpx, pytest；前端 vanilla HTML/CSS/JS；GitHub Actions + Pages。

## Global Constraints（摘自 spec，全任务生效）

- 数据契约以 spec §4 build.py 输出为准；前端只读 `site/data/radar.json`、`site/data/trends.json`。
- 0商品=失败：任何解析结果为空的品类按失败处理，绝不用空数据覆盖旧数据。
- TikTok 成功判定必须校验业务码（`code==0` 或 `BaseResp.StatusCode==0`）且 items 非空。
- 价格解析不得假设 `$`（本机在 Aruba 会出 AWG；CI 为 USD）。
- 1688 主链接 = `https://m.1688.com/offer_search/-{GBK字节HEX大写}.html`；fallback = `https://s.1688.com/selloffer/offer_search.htm?keywords={UTF8%编码}&charset=utf8`。
- 图片一律同源引用 `data/img/*.jpg`，前端不得热链外部图。
- cron 分钟错开整点：`17 */6 * * *`；deploy 用 upload-pages-artifact@v5 + deploy-pages@v5。
- 提交信息末尾带 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

## File Structure

```
scraper/
  config.py        品类/常量/路径（唯一配置点）
  util.py          日志、UTC时间、JSON读写（排序键+缩进2固定排版）
  translate.py     translate_many(), to_keyword_zh(), url_1688(), url_1688_fallback()
  movers.py        load_snapshots(), save_snapshot(), prune_snapshots(), compute_surge()
  tiktok.py        fetch_hashtags() -> list[dict]（校验业务码）
  amazon.py        fetch_category(page,slug,list_kind) -> list[dict]（recs-list主+gridItem富化）, probe_real_movers()
  images.py        mirror_images(products), prune_unused(products)
  build.py         main() 管线编排 + tiktok_match() + 失败/stale策略 + 退出码
  requirements.txt
tests/
  test_translate.py test_movers.py test_build.py test_amazon_parse.py
  fixtures/amazon_zg_sample.html
site/
  index.html css/style.css js/app.js manifest.webmanifest icon.svg
  data/ (radar.json, trends.json, img/ — 由管线生成)
data/ (snapshots/, translations.json — 由管线生成)
.github/workflows/radar.yml
README.md  .gitignore
```

---

### Task 1: 脚手架 + config/util（含固定JSON排版）

**Files:** Create: `scraper/config.py`, `scraper/util.py`, `scraper/requirements.txt`, `.gitignore`, `tests/__init__.py`（空）, `scraper/__init__.py`（空）

**Interfaces (Produces):**
- `config.CATEGORIES: list[dict]` — `{"id","zh","slug"}`，6品类：electronics/beauty/toys-and-games/kitchen/home-garden/sporting-goods（slug 在 Task 5 实测校正）
- `config.ROOT: Path`（仓库根，`Path(__file__).resolve().parents[1]`）、`config.SITE_DATA`, `config.SNAP_DIR`, `config.TRANS_CACHE`, `config.IMG_DIR`
- `util.now_utc() -> datetime`；`util.iso(dt) -> str`；`util.write_json(path, obj)`（`ensure_ascii=False, indent=2, sort_keys=True` + 尾换行）；`util.read_json(path, default)`
- `util.log(msg)`（stderr 带时间戳）

- [ ] requirements.txt: `playwright==1.*`, `httpx`, `pytest`；`.gitignore`: `__pycache__/ .venv/ *.pyc`
- [ ] 实现 config.py/util.py（代码量小，直接写）
- [ ] `python -m venv .venv && .venv/Scripts/pip install -r scraper/requirements.txt && .venv/Scripts/playwright install chromium`
- [ ] Commit `feat: scaffold scraper config and utils`

### Task 2: translate.py（TDD）

**Files:** Create: `scraper/translate.py`, Test: `tests/test_translate.py`

**Interfaces (Produces):**
- `to_short_title(title_en: str) -> str` — 首个`,`/` - `/`(`/`|`前截断、压空格
- `url_1688(kw_zh: str) -> str | None` — GBK可编字符过滤后编hex；全滤空返回None
- `url_1688_fallback(kw: str) -> str`
- `translate_many(texts: list[str], cache_path: Path) -> dict[str,str]` — 缓存命中跳过；Google gtx（0.6s间隔，429退避2次）→ MyMemory 兜底；失败项不入结果；每次调用后写回缓存
- `to_keyword_zh(title_zh: str) -> str` — ≤30字符截断

- [ ] **失败测试**（节选，全部先写）：
```python
def test_url_1688_gbk_hex():
    assert translate.url_1688("手机") == "https://m.1688.com/offer_search/-CAD6BBFA.html"
def test_url_1688_strips_non_gbk():
    assert "CAD6BBFA" in translate.url_1688("手机\U0001F525")  # emoji剔除
def test_url_1688_all_non_gbk_returns_none():
    assert translate.url_1688("\U0001F525") is None
def test_short_title_truncates():
    assert translate.to_short_title("Mini Fan, Portable 3-Speed (Pink)") == "Mini Fan"
def test_translate_many_uses_cache(tmp_path, monkeypatch):
    p = tmp_path/"c.json"; p.write_text('{"Mini Fan":"迷你风扇"}', encoding="utf8")
    called = []
    monkeypatch.setattr(translate, "_google_one", lambda t: called.append(t) or "X")
    out = translate.translate_many(["Mini Fan"], p)
    assert out == {"Mini Fan": "迷你风扇"} and called == []
```
- [ ] `pytest tests/test_translate.py -v` → FAIL（模块未实现）
- [ ] 实现（gtx: `GET translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q=`，取 `json[0][0][0]`；MyMemory 带 `de=` 邮箱）→ PASS
- [ ] Commit `feat: translation with cache and 1688 url builders`

### Task 3: movers.py（TDD）

**Files:** Create: `scraper/movers.py`, Test: `tests/test_movers.py`

**Interfaces:**
- Consumes: `util.write_json/read_json`
- Produces: `save_snapshot(items, when)`（items=`[{asin,list,category,rank}]`，文件名`%Y%m%dT%H%M%SZ.json`）；`pick_baseline(now) -> dict[str,int] | None`（键 `f"{list}:{category}:{asin}"`，选距now 20–28h最近者，否则最老；无快照→None）；`compute_surge(current, baseline) -> list[dict]`（附加 rank_prev/rank_delta/rank_pct/is_new_entry/surge_rank，delta>0 或 NEW 才上榜，NEW按cur rank插序，综合取30）；`prune_snapshots(now, keep_days=14)`

- [ ] **失败测试**（核心断言）：
```python
def test_surge_ranks_by_pct_and_marks_new():
    base = {"bestsellers:electronics:A": 50, "bestsellers:electronics:B": 10}
    cur = [dict(asin="A",list="bestsellers",category="electronics",rank=5),
           dict(asin="B",list="bestsellers",category="electronics",rank=12),
           dict(asin="C",list="bestsellers",category="electronics",rank=3)]
    out = movers.compute_surge(cur, base)
    a = next(x for x in out if x["asin"]=="A")
    assert a["rank_prev"]==50 and a["rank_delta"]==45 and a["surge_rank"]>=1
    assert next(x for x in out if x["asin"]=="C")["is_new_entry"] is True
    assert all(x["asin"]!="B" for x in out)  # 跌了不上榜
def test_pick_baseline_prefers_24h_window(tmp_path): ...
def test_prune_keeps_14_days(tmp_path): ...
```
- [ ] FAIL → 实现 → PASS → Commit `feat: snapshot store and surge computation`

### Task 4: tiktok.py（TDD，网络mock + 实测冒烟）

**Files:** Create: `scraper/tiktok.py`, Test: `tests/test_build.py::test_tiktok_*`（mock httpx）

**Interfaces (Produces):** `fetch_hashtags(limit=50) -> list[dict]`：POST `https://ads.tiktok.com/CreativeOne/KnowledgeAPI/GetHashtagList` body `{"timeRange":7,"countryCode":"US","page":n,"limit":20}`，headers UA/Origin/Referer/Content-Type；响应校验 `code==0 or BaseResp.StatusCode==0`，items空或码非0 → `raise TikTokError`；输出 `{name, rank, posts, curve}`。

- [ ] mock测试：非0业务码→raise；正常→字段映射正确 → FAIL → 实现 → PASS
- [ ] 冒烟：`python -c "from scraper.tiktok import fetch_hashtags; print(fetch_hashtags(limit=5)[:2])"` 出真实数据
- [ ] Commit `feat: tiktok hashtag client with business-code validation`

### Task 5: amazon.py（fixture解析测试 + 本地实抓）

**Files:** Create: `scraper/amazon.py`, `tests/fixtures/amazon_zg_sample.html`（实抓存样）, Test: `tests/test_amazon_parse.py`

**Interfaces (Produces):**
- `parse_zg_html(html) -> list[dict]` — 纯函数：主源 `div[data-client-recs-list]` 属性JSON（id→asin, metadataMap["render.zg.rank"]→rank），`#gridItemRoot` 富化 title/price/rating/ratings_count/image（`data-a-dynamic-image` 选≥400px最小图）；价格取文本原样（不假设币种符号）
- `fetch_category(pw, slug, kind) -> list[dict]` — kind∈{bestsellers,new-releases}；URL `https://www.amazon.com/gp/{'bestsellers' if kind=='bestsellers' else 'new-releases'}/{slug}` + `?pg=2`；页间 2–5s 随机延时；单页去重合并；**空结果 raise CategoryEmpty**
- `probe_real_movers(pw) -> bool`

- [ ] 先写 fixture 获取脚本跑一次真抓存样（本机IP），再写解析测试：
```python
def test_parse_zg_sample_has_50_ranked_items():
    items = amazon.parse_zg_html(FIXTURE.read_text(encoding="utf8"))
    assert len(items) >= 45 and all(i["asin"] and i["rank"]>0 for i in items)
    assert sum(1 for i in items if i.get("title")) >= 25  # 服务端渲染30条有富化
def test_parse_empty_grid_returns_empty():
    assert amazon.parse_zg_html('<div data-client-recs-list="[]"></div>') == []
```
- [ ] FAIL → 实现 → PASS；本地实抓6品类冒烟确认条数
- [ ] Commit `feat: amazon zg scraper with recs-list primary parse`

### Task 6: images.py + build.py（管线契约，TDD核心逻辑）

**Files:** Create: `scraper/images.py`, `scraper/build.py`, Test: `tests/test_build.py`

**Interfaces:**
- `images.mirror(products) -> None`（下载缺失图到 `IMG_DIR/{asin}.jpg`，失败置 image=None 并剔卡）；`images.prune(products)`
- `build.tiktok_match(title_en, hashtags) -> list[str]`（小写去非字母数字后子串匹配，标签长度≥4才参与，防"fan"误伤）
- `build.main() -> int` — 编排：抓取（品类级 try/except → stale回填上次radar.json同品类数据）→ 翻译 → 镜像 → 快照+surge → 组装契约JSON → 写盘；返回退出码 0全好/2部分stale/1全失败（radar.json不写）

- [ ] 测试 tiktok_match、stale回填、契约字段完整性（对照 spec §4 键名逐一断言）→ FAIL → 实现 → PASS
- [ ] Commit `feat: pipeline orchestrator with stale fallback and contract output`

### Task 7: 本地端到端实跑

- [ ] `.venv/Scripts/python -m scraper.build`；检查 radar.json 条目数、中文翻译、1688链接可点、图片入 site/data/img/
- [ ] 首跑无基线→飙升榜空属预期；间隔后二跑（或造老快照）验证surge出数
- [ ] Commit `chore: first real data snapshot`

### Task 8: 前端（manga红黑，浏览器实迭代）

**Files:** Create: `site/index.html`, `site/css/style.css`, `site/js/app.js`, `site/manifest.webmanifest`, `site/icon.svg`

**Interfaces (Consumes):** radar.json/trends.json 契约（spec §4）。

设计系统（锁定）：bg `#0e0e0e`、红 `#e60023`、纸白 `#f5f2ea`、描边 `3px solid #000` 内白外红双层、硬阴影 `4px 4px 0`、halftone 背景 `radial-gradient` 网点、标题字体 Bangers（Google Fonts，`font-display:swap`）+ 中文系统黑体加粗、贴纸角标 `rotate(-4deg)`。
结构与行为（锁定）：顶栏(logo+更新时间+stale黄条) / tabs(🔥📈🆕🎵) / 品类chips横滚 / 2列卡片grid / 全屏图层(真img无遮罩) / 状态角标localStorage(`hotradar_status`) / 保存图片 `canShare({files})→share : a[download]`，catch→toast"长按图片保存" / 复制品名 Clipboard→execCommand降级 / fetch `{cache:'no-store'}` 失败显重试。

- [ ] 写三件套+manifest；`python -m http.server` 起本地服务
- [ ] 浏览器手机视口(375×812)逐tab截图迭代设计至满意；桌面视口回归
- [ ] Commit `feat: manga-style mobile frontend`

### Task 9: workflow + README

**Files:** Create: `.github/workflows/radar.yml`, `README.md`

radar.yml（锁定要点，完整写出）：
```yaml
name: radar
on:
  schedule: [{cron: "17 */6 * * *"}]
  workflow_dispatch:
concurrency: {group: radar, cancel-in-progress: false}
jobs:
  scrape:
    runs-on: ubuntu-latest
    permissions: {contents: write}
    outputs: {status: ${{ steps.run.outputs.status }}}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11", cache: pip, cache-dependency-path: scraper/requirements.txt}
      - run: pip install -r scraper/requirements.txt && playwright install --with-deps chromium
      - id: run
        run: |
          set +e; python -m scraper.build; code=$?
          echo "status=$code" >> "$GITHUB_OUTPUT"
          [ "$code" = "1" ] && exit 1; exit 0
      - run: |
          git config user.name "radar-bot"; git config user.email "actions@github.com"
          git add -A; git diff --cached --quiet && exit 0
          git commit -m "data: $(date -u +%FT%TZ)"; git pull --rebase; git push
  deploy:
    needs: scrape
    runs-on: ubuntu-latest
    permissions: {pages: write, id-token: write}
    environment: {name: github-pages, url: ${{ steps.d.outputs.page_url }}}
    steps:
      - uses: actions/checkout@v4
        with: {ref: main}
      - uses: actions/upload-pages-artifact@v5
        with: {path: site}
      - id: d
        uses: actions/deploy-pages@v5
  report:
    needs: [scrape, deploy]
    runs-on: ubuntu-latest
    steps:
      - run: '[ "${{ needs.scrape.outputs.status }}" = "0" ] || { echo "partial stale"; exit 1; }'
```
- [ ] 写 README（中文：是什么/网址/怎么改品类/故障灯说明）
- [ ] Commit `feat: scheduled scrape+deploy workflow`

### Task 10: 建仓上线验证

- [ ] `gh repo create Yzaruba/hot-radar --public --source . --push`
- [ ] `gh api -X POST repos/Yzaruba/hot-radar/pages -f build_type=workflow`（Pages源=Actions）
- [ ] `gh workflow run radar && gh run watch` → 绿灯
- [ ] 浏览器开 `https://yzaruba.github.io/hot-radar/`：四tab渲染、图片加载、1688链接真开搜索页、时间戳正确；手机视口复验
- [ ] Commit（如有修正）+ 推送

### Task 11: 对抗式审查 + 修复

- [ ] Workflow 多agent审查（正确性/移动端兼容/YAML/安全 四维 + 逐发现复核）
- [ ] 确认项修复、回归测试、推送、复验线上

## Self-Review

- Spec覆盖：§2数据源→T4/T5；§3架构→T9/T10；§4各模块→T2–T6；§5前端→T8；§6测试→各task+T7/T10/T11；§7风险对策（0守卫T5/T6、金丝雀T5、缓存T2、fallback T2）✓
- 占位符扫描 ✓（fixture在T5现场生成属实施动作非占位）
- 接口一致性：`compute_surge`键名、契约字段与spec §4一致 ✓
