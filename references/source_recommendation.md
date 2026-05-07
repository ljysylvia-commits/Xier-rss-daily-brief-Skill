# 信源推荐

> 用途：当用户没有可用 `references/sources.md`，或明确要求推荐信源时，按用户画像生成一组可 review 的 starter sources。

## 目标

推荐一组匹配用户画像、目标受众、主题和日报格式的初始信源。输出是候选方案，不是自动抓取清单。

## 需要推导或询问的信息

优先使用已有对话和 `PROFILE.md`。缺失时再询问：

- 读者角色：founder、operator、investor、engineer、researcher、marketer、creator、student 等
- 目标受众：无、内部团队、公开读者、学生、高管、技术读者、社区 stakeholder 等
- 主题：climate、policy、AI、software infrastructure、health、finance、design、research、行业垂直领域等
- 语言偏好：`zh`、`en` 或 `mixed`
- 输出目标：decision brief、research triage、public briefing material、market scan、competitive tracking
- 格式偏好：Markdown、HTML 或两者

## 推荐组合

首次运行建议 6-12 个信源，规模要小到方便 debug。

| 类型 | 作用 | 典型占比 |
|---|---|---|
| Core authority | 定义用户领域的高信号权威来源 | 30-50% |
| Applied practice | 有工作流、案例或实践细节的博客 / newsletter / podcast | 20-35% |
| Counter signal | 防止共识漂移的反向或批判性来源 | 10-20% |
| Broad discovery | 用于偶发发现的宽流，噪声高时应强降权 | 10-20% |

reader-only 技术用户应减少 broad discovery，优先工程 / 研究信源。有目标受众的用户，应加入更多可解释案例、公开例证和可复用证据。

## 信源类型

优先选择稳定公开 RSS / Atom。仅当没有 RSS 且页面公开时，才使用 archive scraping。

| 类型 | 适合内容 | 备注 |
|---|---|---|
| RSS / Atom | 稳定每日自动化 | 默认首选 |
| Newsletter archive RSS | 长文分析、作者信号 | 仅使用公开 archive |
| Engineering / domain blogs | 技术、政策、行业、实践细节 | 对专业画像通常高价值 |
| Podcast feeds / show notes | 专家访谈和长语境 | 常常只有摘要，深度要诚实标注 |
| Broad aggregators | 发现异常和弱信号 | 噪声高，应标记为 probe 或 broad discovery |

## 候选输出格式

写入 `references/sources.md` 前，先给用户看：

| name | type | url_primary | why it fits | expected value | noise risk | stability level |
|---|---|---|---|---|---|---|

然后让用户 approve、remove 或 add sources。如果用户已经明确要求直接继续，可写入 starter list 并运行 `healthcheck --probe-sources`。

## Source registry 字段

写入 `references/sources.md` 时使用以下 schema：

```markdown
### 1. Source Name
- `url_primary`: `https://example.com/feed`
- `url_fallback`: `https://example.com/`
- `fetch_method`: `rss`
- `freshness`: `daily`
- `depth`: `full_text`
- `lang`: `en`
- `priority`: `core_authority`
- `note`: 客观信源说明，以及为什么适合当前 profile。
```

可选值：

- `fetch_method`: `rss`, `archive_scrape`, `hybrid`
- `freshness`: `daily`, `weekly`, `monthly`, `irregular`
- `depth`: `full_text`, `rich_description`, `summary_only`
- `lang`: `en`, `zh`, `mixed`
- `priority`: 自由文本评分提示，例如 `core_authority`, `applied_practice`, `counter_signal`, `broad_discovery`, `model_systems_engineering`, `climate_policy`, `public_health_signal`

`stability level` 建议使用：

- `rss_stable`：RSS / Atom 稳定，适合自动化。
- `archive_probe`：公开 archive 可访问，但需要内容质量 probe。
- `official_but_no_feed`：官方公开页面但没有稳定 feed。
- `high_noise_broad_discovery`：宽流发现源，必须强降噪。

## Starter pack 示例

以下只是示例，不是默认信源。生产使用前必须验证可访问性。

### 气候适应分析师，面向公开读者

- Yale Climate Connections —— 气候报道和公共沟通
- Carbon Brief —— 气候科学、政策和证据解释
- FEMA Blog —— 应急管理和韧性实践
- Urban Institute —— 城市政策和公共项目研究
- NOAA Climate.gov —— 公共气候数据和教育
- Grist —— 气候政策和社区影响报道
- Heatmap News —— 能源和气候转型报道
- 地方或区域机构 RSS —— 仅在公开且稳定时使用

### Reader-only ML / Infra 研究者

- Cloudflare Blog —— infra、安全、性能和运维事件
- Practical AI —— 应用 ML 和生产实践讨论
- Spotify Engineering —— 大规模产品工程
- Simon Willison —— LLM tooling、evals、安全和工程笔记
- The Gradient —— ML research essays
- Google Research Blog —— 模型和研究公告
- Hacker News RSS —— 仅 broad discovery，噪声高
- arXiv category feeds —— 仅当用户需要论文密集型报告时使用

### 公共卫生政策读者

- CDC public feeds —— 公共卫生更新和指南
- WHO news releases —— 全球健康政策信号
- Health Affairs Blog —— 政策和系统分析
- KFF —— 健康政策解释和数据
- STAT News public feeds —— 生物医学和卫生系统新闻
- 地方卫生部门 feed —— 公共机构语境

## 质量规则

- 不要加入 login-gated、cookie-gated、CAPTCHA-gated、paywalled、X/Twitter、WeChat、Xiaohongshu、TikTok 或私密社区信源。
- 第一次运行不要推荐超过 12 个 starter sources。
- 不要混入当前 profile 之外的私人兴趣。
- broad discovery 信源要明确标记高噪声，并预期由评分层过滤。
- 可能不稳定的信源标为 `probe`，并解释原因。
- 用户确认信源后，先运行 source probe 或 fetch smoke test，再视为生产可用。
- source probe 不只看 HTTP 200；对 archive source 还要检查是否能发现文章级链接、标题和发布时间。
