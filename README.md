# 热品雷达 Hot Radar 🔴⚫

美区热品选品雷达：**Amazon 榜单 + 自算24h飙升 + TikTok 热标签**，手机打开就能用，一键跳 1688 搜同款。

**📱 访问地址：https://yzaruba.github.io/hot-radar/**（手机浏览器打开 → 分享 → 添加到主屏幕，就像装了个App）

## 它每6小时自动做什么

1. 抓 Amazon 美区 6 个品类的**畅销榜 + 新品榜** Top 100（官方 Movers & Shakers 已对机器人关闭，所以对比 24h 前的排名快照**自己算飙升榜**——口径一致）
2. 抓 TikTok Creative Center **美区热标签**（7日热度曲线，覆盖15个行业）
3. 英文品名自动翻译成**中文关键词**（结果缓存在仓库里）
4. 商品图**镜像到本站**（所以「保存图片」总是好使）
5. 生成 JSON → 提交 → 自动部署到 GitHub Pages

## 页面怎么用

- 🔥 **飙升** / 📈 **畅销** / 🆕 **新品** / 🎵 **TikTok** 四个底部标签页
- 卡片：**去1688搜**（中文词直达1688搜索）· 💾 保存图片（存相册后可去1688拍照搜图）· 📋 复制英文品名
- 点商品图 → 大图页（也可以长按图片保存）
- 卡片右上角点一下循环标记：**已定样 → 已上架 → 放弃**（存在你手机本地）
- 商品标题命中 TikTok 热标签会亮 🎵 标——多信号确认的品更稳

## 改配置

- 品类列表：[scraper/config.py](scraper/config.py) 的 `CATEGORIES`
- 抓取频率：[.github/workflows/radar.yml](.github/workflows/radar.yml) 的 `cron`

## 状态灯（Actions 页面）

- 🟢 全部新鲜数据
- 🔴 **看日志区分**：`partial failure` = 部分品类沿用旧数据（页面顶部也会显示黄条警告）；抓取全挂 = 保留旧数据不部署
- 页面顶部若出现 🎉 = Amazon 官方飙升榜解封了，可以升级抓真榜

## 本地开发

```bash
python -m venv .venv && .venv/Scripts/pip install -r scraper/requirements.txt
.venv/Scripts/playwright install chromium
.venv/Scripts/python -m pytest tests/          # 单元测试
.venv/Scripts/python -m scraper.build          # 完整跑一次数据
cd site && python -m http.server 8000          # 本地预览
```

数据源现状（2026-07 实测）与完整设计见 [docs/superpowers/specs/](docs/superpowers/specs/2026-07-19-hot-radar-design.md)。
