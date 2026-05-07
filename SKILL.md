---
name: rss-daily-brief
description: Generate a configurable, noise-reducing daily brief from public RSS, Atom, archive, newsletter, podcast show-note, or engineering-blog sources. Use when the user asks to run or customize an RSS daily brief, daily report, daily digest, newsletter brief, source-monitoring brief, information filter, or Markdown/HTML report. If the user has no source list yet, the skill can recommend a starter source pack from the user's profile, target audience, and report goals, then let the user add their own sources before fetching. The skill fetches recent public web sources, deduplicates stories, scores them against a configurable reader profile, maps reader/audience value, synthesizes an outlook, and renders Markdown, themed HTML, or both. It does not handle login-gated, cookie-gated, CAPTCHA-gated, X/Twitter, WeChat, Xiaohongshu, or other anti-scrape sources.
---

# RSS Daily-Brief

## 文字规范

- 面向用户的说明、确认问题和日报内容使用用户配置的输出语言；默认中文。
- 文件名、命令、JSON key、枚举值、tier、theme、URL、Agent 名称保留英文。
- 不要把 `cluster_id`、`lint_fail`、内部文件路径、运行状态码等内部语言直接写进用户可见日报。
- 当输出语言为中文时，英文信源内容需要翻译或概括成中文；低相关 `others` 也要提供中文标题和中文要点。

## 这个 Skill 做什么

读取或创建 `references/sources.md`，抓取公开信源，去重聚类，按 `references/PROFILE.md` 和评分规则筛选内容，生成读者视角和可选目标受众视角的价值解释，最后渲染配置指定的输出格式：

- `outputs/daily-brief/YYYY-MM-DD.md`
- `outputs/daily-brief/YYYY-MM-DD.html`

开源版默认使用 demo 配置。生产使用前，必须替换 demo 用户画像和 demo 信源。

## 配置入口

| 文件 | 用途 |
|---|---|
| `config/report_config.json` | 报告标题、输出语言、输出格式、HTML 主题、功能开关 |
| `references/run_modes.md` | setup、tuning、stable 三种运行模式 |
| `references/profile_onboarding.md` | 推导并确认用户画像、评分规则和价值视角 |
| `references/PROFILE.md` | 用户画像、目标受众和评分偏好 |
| `references/scoring_profile.json` | Scorer 使用的结构化评分规则 |
| `references/angle_config.json` | Reader/Audience angle key 与中文 label 的单一真相源 |
| `references/sources.md` | 公开 RSS / archive / newsletter / podcast 信源表 |
| `references/source_recommendation.md` | 用户没有信源时如何推荐初始信源 |
| `references/feedback_loop.md` | 用户反馈如何沉淀成配置或模板改动 |
| `references/prompt_hygiene.md` | 防止 demo 泄漏、内部语言泄漏和提示词漂移 |
| `references/agents/scorer-rubric.md` | 通用评分锚点；需结合 `PROFILE.md` 使用 |
| `references/pillar_config.json` | 高级可选内容支柱配置；默认不启用 |
| `references/perspectives/reader.md` | 读者视角价值判断规则 |
| `references/perspectives/audience.md` | 可选目标受众视角价值判断规则 |
| `assets/daily.md.j2` | Markdown 模板 |
| `assets/daily.html.j2` | HTML 模板，支持 `light`、`dark` |

输出格式配置：

```json
{
  "outputs": {
    "formats": ["markdown", "html"],
    "directory": "outputs/daily-brief"
  }
}
```

`outputs.formats` 支持 `["markdown"]`、`["html"]`、`["markdown", "html"]`。运行时可用 `--output-formats markdown,html` 覆盖。

HTML 主题配置：

```json
{
  "html_theme": "light"
}
```

`html_theme` 支持 `light`（明亮版）和 `dark`（黑夜版）。运行时可用 `--html-theme` 覆盖。

## 运行模式

运行前先读 `references/run_modes.md`，并检查 `config/report_config.json.lifecycle.mode`。如果要改提示词、onboarding、反馈闭环或 stable 运行范围，也要读 `references/prompt_hygiene.md`。

| 模式 | 含义 | 运行路径 |
|---|---|---|
| `setup` / `demo` | 首次配置，或 demo 文件尚未替换 | Step -2、Step -1，然后 Step 0-6 |
| `tuning` | 用户正在调评分、信源、价值视角、输出格式或 HTML 样式 | Step 7，然后重跑 Step 0-6 |
| `stable` | 用户已确认配置，可每日自动运行 | 只跑 Step 0-6 |

Step -2、Step -1、Step 7、Step 8 不是每日自动化步骤。stable 模式下，除非文件缺失、healthcheck 失败，或用户明确要求修改画像、信源、评分、反馈或自动化配置，否则只执行 Step 0-6。

不要把 demo 示例当成用户身份。如果 `PROFILE.md`、`sources.md`、价值视角、输出格式或 HTML 主题仍明显是 demo，生产运行前必须先让用户确认替换。

## 边界

| 支持 | 不支持 |
|---|---|
| RSS / Atom feeds | X / Twitter 登录或 API 工作流 |
| 公开 archive 页面 | 微信、小红书、TikTok、私密社群 |
| 普通 HTTP 可访问的 newsletter 页面 | CAPTCHA、付费墙、cookie 登录、浏览器会话抓取 |
| podcast show notes | 私人数据或浏览历史报告 |

如果信源需要登录、cookie、验证码或浏览器自动化才能访问，停止执行，并说明它不属于此 Skill 的范围。

## 运行链路

### Step -2 · 缺少用户配置时做画像配置

仅 setup / tuning 使用。stable 日常运行跳过。

如果 `references/PROFILE.md`、`references/perspectives/reader.md` 或 `references/perspectives/audience.md` 仍像 demo，不要把它们当成用户真实偏好。

1. 读取 `references/profile_onboarding.md`。
2. 第一轮只推导读者画像、P1 / P2 / P3 评分规则、降权规则、加分信号和读者价值视角。
3. 用户确认第一轮后，立即写入 `PROFILE.md`、`scoring_profile.json`、`perspectives/reader.md` 和 `angle_config.json`。
4. 第二轮再确认是否有目标受众；如果有，推导目标受众画像和 audience value angles；如果没有，关闭 `features.audience_view`。
5. 用户确认第二轮后，立即写入 `perspectives/audience.md`、`angle_config.json` 和 `report_config.json`。
6. 第三轮再进入信源推荐；第四轮再确认 Markdown 结构和 HTML 明亮版 / 黑夜版。

开源 demo profile 只是占位。不得复用任何其他用户的私人画像、评分规则、信源偏好或价值视角。

### Step -1 · 没有信源时做信源配置

仅 setup / tuning 使用。stable 日常运行跳过，除非 `sources.md` 缺失或用户要求修改信源。

如果 `references/sources.md` 缺失、为空或仍明显是 demo，不要直接抓取。

1. 读取已确认的 `references/PROFILE.md` 和 `config/report_config.json`。
2. 读取 `references/source_recommendation.md`。
3. 基于用户角色、目标受众、主题、语言和输出目标推荐初始信源。
4. 用短表格展示：name、type、URL、why it fits、expected noise risk、core / probe / broad-discovery。
5. 邀请用户补充自己的信源，或删除弱相关推荐。
6. 用户确认后，把最终信源写入 `references/sources.md`，再进入 Step 1。

推荐信源只是候选。只有 `scripts/healthcheck.py --root . --probe-sources` 或 `scripts/fetch.py` 实际测试后，才能说该信源可访问。

### Step 0 · 准备运行目录

```bash
RUN_DATE=$(date +%Y-%m-%d)
RUN_DIR="./tmp/${RUN_DATE}"
python3 scripts/cleanup_tmp.py --root . --retention-days 7
mkdir -p "${RUN_DIR}/clusters" "${RUN_DIR}/value_mapped_reader" "${RUN_DIR}/value_mapped_audience"
```

写入 `run_context.json`，包含运行日期、已知模型名和运行目录。

### Step 1 · 抓取

```bash
python3 scripts/fetch.py \
  --sources references/sources.md \
  --output "${RUN_DIR}/raw_items.jsonl" \
  --log "${RUN_DIR}/fetcher.log" \
  --state-file "${RUN_DIR}/.fetcher_state.json" \
  --coverage-hours 24
```

### Step 2 · 去重聚类

```bash
python3 scripts/dedupe.py \
  --input "${RUN_DIR}/raw_items.jsonl" \
  --output-dir "${RUN_DIR}/clusters/" \
  --index "${RUN_DIR}/clusters_index.json"
```

### Step 3 · 评分

使用 AI：

- system prompt: `references/PROFILE.md` + `references/scoring_profile.json` + `references/agents/scorer-rubric.md` + `references/agents/scorer.md`
- user input: `${RUN_DIR}/clusters_index.json`
- output: `${RUN_DIR}/scored.json`

按 `references/agents/scorer.md` 校验 JSON。

### Step 3b · 翻译 Others

当 `config/report_config.json` 设置 `translate_others_to_output_language = true` 时，对 `tier = others` 的条目生成 `title_zh` 和 `gist_zh`，写入 `${RUN_DIR}/others_translated.json`。

### Step 4 · 价值映射

对 must-read / recommended / optional 条目运行 Reader VM：

- system prompt: `references/PROFILE.md` + `references/sources.md` + `references/perspectives/reader.md` + `references/agents/value-mapper-reader.md`
- input: `${RUN_DIR}/clusters/{cluster_id}.json`
- output: `${RUN_DIR}/value_mapped_reader/{cluster_id}.json`

如果 `features.audience_view = true`，在 Reader VM 之后运行 Audience VM：

- 默认 system prompt: `references/PROFILE.md` + `references/sources.md` + `references/perspectives/audience.md` + `references/agents/value-mapper-audience.md`
- 高级可选：仅当 `features.pillar_mapping = true` 时加入 `references/pillar_config.json`，并要求 Audience VM 输出 `pillars`
- input: cluster JSON + 对应 reader VM JSON
- output: `${RUN_DIR}/value_mapped_audience/{cluster_id}.json`

合并：

```bash
python3 scripts/merge_perspectives.py \
  --reader-dir "${RUN_DIR}/value_mapped_reader" \
  --audience-dir "${RUN_DIR}/value_mapped_audience" \
  --scored "${RUN_DIR}/scored.json" \
  --output "${RUN_DIR}/value_mapped.json" \
  --angle-config ./references/angle_config.json \
  --dedup-threshold 0.72
```

如果关闭 Audience VM 或没有 audience 输出，省略 `--audience-dir`；合并脚本会按 reader-only 模式运行。

### Step 5 · 今日判断

使用 AI：

- system prompt: `references/PROFILE.md` + `references/agents/outlook-curator.md`
- input: `${RUN_DIR}/value_mapped.json`
- output: `${RUN_DIR}/outlook.json`

### Step 6 · 渲染

```bash
python3 scripts/render.py \
  --clusters-index "${RUN_DIR}/clusters_index.json" \
  --scored "${RUN_DIR}/scored.json" \
  --value-mapped "${RUN_DIR}/value_mapped.json" \
  --outlook "${RUN_DIR}/outlook.json" \
  --others-translated "${RUN_DIR}/others_translated.json" \
  --fetcher-log "${RUN_DIR}/fetcher.log" \
  --raw-items "${RUN_DIR}/raw_items.jsonl" \
  --run-context "${RUN_DIR}/run_context.json" \
  --report-config ./config/report_config.json \
  --template ./assets/daily.md.j2 \
  --html-template ./assets/daily.html.j2 \
  --output-formats markdown,html
```

可选覆盖：

```bash
python3 scripts/render.py ... --html-theme light
python3 scripts/render.py ... --html-theme dark
python3 scripts/render.py ... --output-formats markdown
python3 scripts/render.py ... --pillar-config ./references/pillar_config.json
```

只有当用户明确需要内容支柱、newsletter 栏目、briefing modules、IP 选题支柱等可复用内容桶时，才传入 `--pillar-config` 并启用 `features.pillar_mapping=true`。开源默认不展示内容支柱。

### Step 7 · 用户反馈路由

仅 setup / tuning 使用。stable 日常运行跳过，除非用户给出新反馈。

渲染后，让用户先 review 日报，再把配置视为 stable。

当用户反馈“太技术了”“这个应该降权”“我更想看政策影响”“这个信源太吵”“HTML 字体太浅”等问题时：

1. 读取 `references/feedback_loop.md`。
2. 判断反馈应落到哪个文件：`scoring_profile.json`、`angle_config.json`、`perspectives/*.md`、`sources.md`、`report_config.json` 或模板文件。
3. 提出具体、可持久化的修改方案，并在编辑配置、评分规则、信源或模板前让用户确认。
4. 应用用户确认的配置或模板改动。
5. 重渲染同一次运行或 fixture。
6. 用具体检查验证变化生效。
7. 用户确认前，保持 `config/report_config.json.feedback.status = "tuning"`。

不要只把反馈留在聊天记忆中。下一次日报必须能从文件中复现这次调整。

### Step 8 · 稳定为每日自动化

仅 setup / tuning 使用。stable 日常运行跳过。

只有当用户画像、评分规则、价值视角、信源列表、报告格式和视觉样式都被确认后，才能标记为 stable。

进入 stable 时：

- 设置 `config/report_config.json.feedback.status = "stable"`；
- 设置 `feedback.open_items = []`，或明确列出延后处理项；
- 只有当用户需要定时运行时，才设置 `automation.enabled = true`；
- 保持 `automation.requires_stable_feedback = true`。

这个 Skill 本身不创建调度器。每日运行应由宿主环境的 cron、CI、task runner 或 automation 功能执行同一条 pipeline。

## 验证

生产自动化前运行：

```bash
bash scripts/bootstrap.sh
python3 scripts/healthcheck.py --root .
python3 scripts/healthcheck.py --root . --probe-sources
```

成功标准：

- 配置指定的输出文件存在：Markdown、HTML 或两者都有。
- stable 模式下，日常执行只走 Step 0-6。
- 用户可见输出中没有内部 `cluster_id`、raw lint key 或运行文件路径。
- 非输出语言的信源片段已翻译或概括成配置指定的输出语言。
- HTML 能在浏览器打开，所选主题可读，并与 Markdown 内容结构一致。
- review 阶段的用户反馈已应用到配置 / 模板文件，或记录在 `feedback.open_items`。
- 提示词改动符合 `references/prompt_hygiene.md`：无私人默认值、无重复规则，且持久化用户可见改动前已确认。

## 新用户首次配置

1. 用 `references/profile_onboarding.md` 第一轮确认读者画像、P1/P2/P3、降权/加权规则和 reader value angles。
2. 用户确认后写入 `PROFILE.md`、`references/scoring_profile.json`、`references/angle_config.json`、`references/perspectives/reader.md`。
3. 第二轮确认是否有目标受众；有则写入 audience 配置，无则关闭 `features.audience_view`。
4. 如果没有信源列表，用 `references/source_recommendation.md` 推荐初始信源；否则编辑 `references/sources.md`。
5. 确认输出格式、日报长度和 HTML 主题；默认 Markdown + HTML，must 3 / recommended 5 / optional 10，主题只选 `light` 或 `dark`。
6. 运行 healthcheck，并用小信源列表做一次短 dry run。
7. 通过 `references/feedback_loop.md` 处理用户反馈；持久化改动前必须先确认方案。
8. 用户确认后，再标记配置为 stable 并安排每日自动化。
