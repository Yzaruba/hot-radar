# 热品雷达 Hot Radar — 设计文档

日期：2026-07-19 ｜ 状态：已批准（用户委托全程执行）

## 1. 目标与背景

为 Goodies 4 Everyone（Aruba 零售店，客群以美国游客为主）做一个**手机浏览器访问的选品雷达网页**：
自动追踪美区正在飙升的商品，卡片式展示（图片+中英文名+涨幅+信号），一键跳 1688 搜同款、一键保存商品图（用于 1688 拍照搜图定样品）。

- 零成本运行：GitHub Actions 定时抓取 + GitHub Pages 托管，无服务器。
- 使用者只有店主本人，手机为主（iPhone/Android 均需可用）。
- 风格：manga 红黑风（Goodies 品牌调性），由本项目直接设计（不再依赖 Claude Design 原型文件）。

## 2. 数据源决策（2026-07-19 实测结论）

| 原计划 | 实测现状 | 采用方案 |
|---|---|---|
| TikTok Creative Center 热品榜 | **板块已随 TikTok One 改版下线**（301实测；付费爬虫服务也标记"已移除"） | 改用官方匿名热标签接口 `POST ads.tiktok.com/CreativeOne/KnowledgeAPI/GetHashtagList`（美区、7/30天、热度曲线；实测可用且有公开仓库每日从 Actions 成功调用） |
| Amazon Movers & Shakers | **2026-05 中起对数据中心 IP 返回空榜**（HTTP 200 + 空列表，真 Chrome 亦然） | 抓**畅销榜 + 新品榜**（vanilla headless Playwright 从 Actions 实测可用），存快照，**自算 24h 排名飙升榜**（即 M&S 的定义）；每次运行探测真 M&S 页作为"解封金丝雀" |

TikTok 信号与商品的连接：商品标题与热标签做关键词交叉匹配，命中则点亮 TikTok🔥 信号标。

## 3. 架构与数据流

```
GitHub Actions（cron: 17 */6 * * *，UTC，+ workflow_dispatch 手动触发）
  scrape job（permissions: contents: write）:
    1. amazon.py    Playwright 抓 6 品类 × (畅销榜+新品榜) × Top100
    2. tiktok.py    GetHashtagList 美区热标签（code!=0 视为失败）
    3. movers.py    与 ~24h 前快照比对 → 飙升榜
    4. translate.py 英→中（Google gtx，MyMemory 兜底，缓存于 data/translations.json）
    5. images.py    镜像商品图到 site/data/img/（同源 → 保存/分享无 CORS 限制），清理失引用图片
    6. build.py     生成 site/data/radar.json + trends.json；写 data/snapshots/
    7. git commit（有变更才提交；jq 风格稳定排版减小 diff）
  deploy job（needs: scrape; permissions: pages: write, id-token: write）:
    checkout main 最新 → upload-pages-artifact(site/) → deploy-pages
  Pages 源设为 "GitHub Actions"（规避 GITHUB_TOKEN 提交不触发分支构建的官方陷阱）
```

- 仓库：`Yzaruba/hot-radar`（公开，Free 计划 Pages 要求）。访问地址 `https://yzaruba.github.io/hot-radar/`。
- 每 6h 一次数据提交即可长期重置 GitHub"60 天不活跃停用定时任务"计时器。
- cron 分钟数错开整点（GitHub 高峰丢任务）。concurrency group 防并发推送冲突。

## 4. 抓取端设计（scraper/，Python 3.11）

### amazon.py
- vanilla Playwright Chromium headless（不用 stealth/代理——实测当前从 Actions 可用）。
- 品类（可配置，`config.py`）：electronics、beauty、toys-and-games、kitchen、home-garden、sporting-goods（实施时以实际 zgbs slug 验证为准）。
- 每品类抓 `/gp/bestsellers/<slug>` 与 `/gp/new-releases/<slug>` 第 1、2 页（Top100）。
- 解析策略（复核agent实测确认）：`data-client-recs-list` JSON 属性为主（含全部 50 条的 ASIN+rank；注意其中 bsms.* 涨幅字段值为空串，**不可用**），30 个服务端渲染的 `#gridItemRoot` 块补充 title/price/rating/image（`data-a-dynamic-image` 取 ~600px 图）。
- 节流：品类间 2–5s 随机延时；503 指数退避重试 ≤3 次。
- **0 商品守卫**：解析出 0 条 = 该品类失败（Amazon 封锁的表现是"假成功"）。
- 金丝雀：每次运行 GET 真 M&S 页一次，解析出>0 条则在日志与 JSON 中标记 `real_movers_available: true`（人工决定切换）。

### tiktok.py
- `POST /CreativeOne/KnowledgeAPI/GetHashtagList`，body `{timeRange:7, countryCode:'US', page, limit}`，浏览器化 headers（UA/Origin/Referer）。翻页取 ≤50 个。
- 成功判定：HTTP 200 **且** `code==0`/`BaseResp.StatusCode==0` 且 items 非空。
- 字段：hashtagName、publishCnt、rankIndex、popularityCurve（7点，归一化0-100）。

### movers.py（自算飙升榜）
- 快照：`data/snapshots/<UTC时间戳>.json`，仅存 `{list, category, asin, rank}` 精简结构；保留 14 天，运行时修剪。
- 对比目标：快照年龄在 8–48h 之间、最接近 24h 者；无合格快照 → 飙升榜为空并在页面提示"数据积累中"（过新=抖动噪声，过老=把慢漂移误标为24h飙升，都不用）。
- 指标：`delta = prev_rank - cur_rank`；`pct = delta / prev_rank * 100`。上榜条件 `delta > 0`。
- 榜单构成（2026-07-19 审查后修订）：真实排名上涨者按 pct 降序优先占位；`NEW`（上次不在 Top100 本次进入）仅统计畅销榜（新品榜天然高流转无信号价值）、按当前排名排序垫底、至多 10 席；基线快照中未观测的 (榜单,品类) 组合整体跳过（防止品类抓取失败一天后被误标 NEW）；每 ASIN 只占一席；总榜 30。

### translate.py
- 主：`translate.googleapis.com/translate_a/single?client=gtx`（无 key）；调用间隔 0.5–1s，429 退避重试。
- 兜底：MyMemory（带 `de=` 邮箱参数提额）。再兜底：沿用缓存/标记未译。
- 缓存 `data/translations.json`（标题→中文），只译新标题。
- `keyword_zh`（1688 搜索词）：标题在首个分隔符（`,`、`-`、`(`、`|`）前截断、去多余空格后翻译，≤30 汉字。

### images.py
- 下载 radar.json 引用的商品图至 `site/data/img/<ASIN>.jpg`（已存在跳过）；运行末删除未被当前 JSON 引用的图。TikTok 头像不镜像。

### build.py 输出契约（前端唯一依赖）

`site/data/radar.json`：
```json
{
  "generated_at": "ISO-8601 UTC",
  "real_movers_available": false,
  "categories": [{"id": "electronics", "zh": "电子", "stale": false}],
  "products": [{
    "asin": "B0XXXXXXX",
    "title_en": "…", "title_zh": "…", "keyword_zh": "…",
    "url_1688": "https://m.1688.com/offer_search/-<GBK大写HEX>.html",
    "url_1688_fallback": "https://s.1688.com/selloffer/offer_search.htm?keywords=<UTF8编码>&charset=utf8",
    "amazon_url": "https://www.amazon.com/dp/<ASIN>",
    "image": "data/img/B0XXXXXXX.jpg",
    "price": "$12.99", "rating": 4.5, "ratings_count": 1234,
    "category": "electronics", "list": "bestsellers|new-releases",
    "rank": 3, "rank_prev": 27, "rank_delta": 24, "rank_pct": 88.9, "is_new_entry": false,
    "surge_rank": 1,
    "signals": {"amazon_surge": true, "tiktok": ["hashtagname"], "new_release": false},
    "first_seen": "2026-07-18"
  }]
}
```
`site/data/trends.json`：
```json
{"generated_at": "…", "hashtags": [{"name": "…", "zh": "…", "rank": 1,
  "posts": 12345, "curve": [0,10,…], "url_1688": "…", "keyword_zh": "…"}]}
```
- 1688 链接构造：`kw.encode('gbk').hex().upper()` 嵌入 m.1688.com 路径（实测格式）；GBK 编不了的字符先剔除，全剔空则退回 fallback URL。
- TikTok 匹配：标题小写去符号后，热标签名（小写）作为连续子串出现于"去空格标题"即命中。
- 失败策略：某品类失败 → 沿用上次该品类数据并标 `stale:true`，流程继续；**全部**品类失败 → 退出码 1，不提交不部署（保住旧数据）；部分失败 → 正常提交部署后以退出码标红运行（deploy 完成后的 report step 失败），确保能看到红灯。

## 5. 前端设计（site/，纯 HTML/CSS/JS，无构建步骤）

**Manga 红黑风**：近黑底（#0e0e0e）+ 品牌红（#e60023）+ 白；卡片粗描边+硬阴影（偏移实色无模糊）；网点（halftone）纹理背景；标题斜切色块、速度线点缀；状态角标做成歪贴的"贴纸"。展示字体 Google Fonts（Bangers 类）+ 系统中文字体。浅色模式不做——黑就是品牌。

结构（单页）：
- 顶栏：LOGO「热品雷达 HOT RADAR」+ 数据更新时间（相对时间，>12h 变黄提示，stale 品类黄条警告）。
- Tab：🔥 飙升榜 ｜ 📈 畅销榜 ｜ 🆕 新品榜 ｜ 🎵 TikTok。
- 品类 chips 横滚（全部/电子/美妆…，飙升榜与榜单页共用）。
- 商品卡（2 列网格）：图、涨幅贴纸（↑88% / NEW）、英文名（2行截断）、中文名、价格+评分、信号 emoji 行、底部按钮行【去1688搜 ｜ 💾 ｜ 📋】。
- 点图 → 全屏查看层（真 `<img>`，无遮罩覆盖，保长按保存；下方大按钮：去1688搜 / 保存图片 / 复制品名 / Amazon 页）。
- TikTok tab：标签卡（#名称、中文、7日曲线 sparkline 内联 SVG、发帖数、去1688搜）。
- 状态标记：卡片角标点击循环 无→已定样→已上架→放弃，localStorage 按 ASIN 存储。
- 「保存图片」实现顺序（实测结论）：fetch 同源图 → blob → `navigator.canShare({files})` ? `navigator.share`（iOS 唯一进相册路径，需用户手势内调用）: `<a download>`（Android 存下载）；异常时提示长按图片保存。
- 「去1688搜」：`window.open(url_1688)`；「复制品名」：Clipboard API，降级 execCommand。
- `manifest.webmanifest`（standalone、theme #0e0e0e、红黑图标）支持"添加到主屏幕"；不做 Service Worker（避免缓存陈旧数据）。
- JSON 加载：`fetch('data/radar.json', {cache:'no-store'})`；失败显示重试按钮。

## 6. 测试与验证

- 纯逻辑单元测试（pytest）：movers 计算、1688 URL/GBK hex、标签匹配、翻译缓存、快照修剪、build 输出契约校验。
- 抓取端本地实跑（本机住宅 IP）产出真实 JSON；注意本机地理位置在 Aruba，价格可能显示 AWG——CI 的美国 runner 会是 USD，价格解析不得写死 `$`。
- 前端用真实 JSON 在浏览器（手机视口）人工过一遍四个 tab + 三个按钮。
- 多 agent 对抗式代码审查（正确性/移动端兼容/workflow YAML/安全）后修复再部署。
- 上线后验证：真实 Pages URL 加载、workflow_dispatch 全流程绿灯、1688 链接真实打开搜索结果。

## 7. 风险与既定对策

- Amazon 收紧到畅销榜 → 0商品守卫报红；备选：自托管 runner（店主家宽）/其他站点榜单/付费 API。
- TikTok 接口无文档随时可变 → code!=0 即失败报红；备选：Playwright 走旧 URL 触发 XHR 拦截。
- gtx 翻译被限 → 缓存 + MyMemory，兜底显示英文。
- 1688 hex 路径变更 → fallback URL + 复制关键词按钮永远可用。
- ToS：个人低频工具、无登录账号、不商业转售数据；风险已向用户说明。

## 8. 后续可扩展（不在本期）

付费 TikTok Shop 商品数据（EchoTik/FastMoss/Apify）作为可插拔数据源；Alibaba 国际站榜单；毛利试算（手填拿货价）；历史曲线页。
