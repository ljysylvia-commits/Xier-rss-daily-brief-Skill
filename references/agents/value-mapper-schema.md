# Value-Mapper · 输出契约 / JSON Schema / 合并规则 / 质量检查

> 主体与调用约定见 `value-mapper-reader.md` 与 `value-mapper-audience.md`。
> 视角规则与 Angle 池见 `../perspectives/reader.md` / `../perspectives/audience.md`。

---

## 1 · 输出契约

### 1.1 Reader VM 产物（`${RUN_DIR}/value_mapped_reader/{cluster_id}.json`）

```json
{
  "meta": {
    "cluster_id": "c_20260426_anthropic_sdk2",
    "date": "2026-04-26",
    "generated_by": "value-mapper-reader",
    "generated_at": "2026-04-26T07:25:00+08:00",
    "model": "claude-sonnet-4-5",
    "input_tokens": 24131,
    "output_tokens": 1842
  },
  "content_mode": "single_article",
  "section_scan": [],
  "title_zh": "热风险仪表盘把脆弱街区排到规划优先级前面",
  "key_tags": ["Heat Risk", "Public Health", "Urban Planning", "Dashboard"],
  "core_content": [
    "新仪表盘把温度、树冠覆盖、老年人口和急救响应压力放到同一张街区地图里",
    "两篇来源都指向同一变化：热风险治理从城市平均值转向街区级资源排序",
    "对规划者有用的不是单个高温新闻，而是哪些区域应该先配降温、巡查和避暑点"
  ],
  "value_blocks": [
    {
      "perspective": "reader",
      "angle": "decision_impact",
      "body": "这条能帮你把热浪报道转成规划优先级：先识别高温、低树冠和弱势人口重叠的街区。"
    },
    {
      "perspective": "reader",
      "angle": "firsthand_evidence",
      "body": "仪表盘把多个公共数据源合并成街区风险排序，比单看气温或灾害通报更适合做政策备忘。"
    }
  ],
  "reading_suggestion": "先看数据口径和街区排序方法，再评估它是否能接入本地规划和公共卫生流程。",
  "warnings": []
}
```

### 1.2 Audience VM 产物（`${RUN_DIR}/value_mapped_audience/{cluster_id}.json`）

```json
{
  "meta": {
    "cluster_id": "demo_heat_risk_dashboard",
    "date": "2026-04-26",
    "generated_by": "value-mapper-audience",
    "generated_at": "2026-04-26T07:27:30+08:00",
    "model": "claude-sonnet-4-5",
    "input_tokens": 28543,
    "output_tokens": 1120
  },
  "value_blocks": [
    {
      "perspective": "audience",
      "angle": "practical_application",
      "body": "城市团队可以先用现有数据做低成本热风险分层，再决定降温中心、树荫和巡查资源的优先顺序。"
    },
    {
      "perspective": "audience",
      "angle": "structural_impact",
      "body": "切入句：**「从平均气温到街区优先级」**——热风险治理开始从宏观气候叙事进入预算、服务和公共卫生资源排序。"
    }
  ],
  "pillars": [],
  "skipped_perspectives": [],
  "warnings": []
}
```

### 1.3 合并产物（`${RUN_DIR}/value_mapped.json`，由 `merge_perspectives.py` 产出）

```json
{
  "meta": {
    "date": "2026-04-26",
    "cluster_count": 9,
    "success_count": 9,
    "failure_count": 0,
    "dedup_threshold": 0.72,
    "audience_enabled": true
  },
  "entries": [
    {
      "meta": {
        "cluster_id": "c_20260426_anthropic_sdk2",
        "reader_model": "claude-sonnet-4-5",
        "audience_model": "claude-sonnet-4-5",
        "generated_at": "2026-04-26T07:30:00+08:00"
      },
      "content_mode": "single_article",
      "section_scan": [],
      "title_zh": "...",
      "key_tags": ["..."],
      "core_content": ["..."],
      "reading_suggestion": "...",
      "value_blocks": [
        {"perspective": "reader",   "angle": "decision_impact", "body": "..."},
        {"perspective": "reader",   "angle": "firsthand_evidence", "body": "..."},
        {"perspective": "audience", "angle": "practical_application", "body": "..."},
        {"perspective": "audience", "angle": "structural_impact", "body": "..."}
      ],
      "pillars": [],
      "skipped_perspectives": [],
      "warnings": []
    }
  ],
  "warnings": []
}
```

下游 `outlook-curator` 与 Writer 读这份合并后的文件。

---

## 2 · JSON Schema（字段约束）

### 2.1 Reader VM 产物字段

| 字段路径 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `meta.cluster_id` | string | ✅ | 与输入 cluster_id 一致 |
| `meta.date` | string | ✅ | `YYYY-MM-DD` |
| `meta.generated_by` | string | ✅ | 固定 `"value-mapper-reader"` |
| `meta.model` | string | ✅ | 子 Agent 运行时实际使用的模型 ID |
| `meta.input_tokens` | number | ✅ | 输入 token 数（自报） |
| `meta.output_tokens` | number | ✅ | 输出 token 数（自报） |
| `content_mode` | string | ✅ | `single_article` / `roundup_digest` / `transcript_long` / `sparse_short` |
| `section_scan` | array<object> | 条件必填 | `content_mode = roundup_digest` 时必填；至少 3 条，除非原文少于 3 个 section |
| `section_scan[].section` | string | 条件必填 | section 标题或语义名 |
| `section_scan[].summary` | string | 条件必填 | 该 section 的事实性短摘要 |
| `section_scan[].relevance` | string | 条件必填 | `high` / `medium` / `low` |
| `section_scan[].selection_decision` | string | 条件必填 | `selected` / `skipped` |
| `section_scan[].reason` | string | 条件必填 | 选择或跳过原因，必须贴合读者画像 |
| `title_zh` | string | ✅ | ≤ 60 中文字 |
| `key_tags` | array<string> | ✅ | 长度 3-5 |
| `core_content` | array<string> | ✅ | 长度 2-8 |
| `reading_suggestion` | string | ✅ | 按 content_type 差异化 |
| `value_blocks` | array<object> | ✅ | 长度 0-4，**2-3 为常态** |
| `value_blocks[].perspective` | string | ✅ | 固定 `"reader"` |
| `value_blocks[].angle` | string | ✅ | 必须是 `perspectives/reader.md` §2 的 key 之一 |
| `value_blocks[].body` | string | ✅ | 40-110 中文字 |
| `skipped_perspectives` | array<object> | — | 可空；每项 `{"视角": "...", "原因": "..."}`（中文字段名，避免日报渲染泄漏英文） |
| `warnings` | array<object> | ✅ | 可空数组；每项 `{type, message, ...}` |

**Reader VM 禁止字段**：`pillars` / `perspective=audience` 的 value_blocks / `daily_outlook`。

### 2.2 Audience VM 产物字段

| 字段路径 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `meta.cluster_id` | string | ✅ | 与输入一致 |
| `meta.generated_by` | string | ✅ | 固定 `"value-mapper-audience"` |
| `meta.model` / `input_tokens` / `output_tokens` | — | ✅ | 同上 |
| `value_blocks` | array<object> | ✅ | 长度 0-3；**允许为空** |
| `value_blocks[].perspective` | string | ✅ | 固定 `"audience"` |
| `value_blocks[].angle` | string | ✅ | 必须是 `perspectives/audience.md` §2 的 key 之一 |
| `value_blocks[].body` | string | ✅ | 40-110 中文字 |
| `pillars` | array<string> | — | 默认空或省略；仅当 `features.pillar_mapping=true` 时长度 0-2，枚举在 `pillar_config.json` |
| `skipped_perspectives` | array<object> | — | 可空；每项 `{"视角": "...", "原因": "..."}` |
| `warnings` | array<object> | ✅ | 可空数组 |

**Audience VM 禁止字段**：base 字段（`title_zh` / `key_tags` / `core_content` / `reading_suggestion`） / `perspective=reader` 的 value_blocks / `daily_outlook`。

### 2.3 合并产物字段

见 §1.3 示例；关键点：
- `value_blocks[]` 合并顺序：Reader 在前，Audience 在后
- `pillars` 仅在 content pillars opt-in 时取自 Audience VM；默认应为空数组
- `skipped_perspectives` 合并来自两侧 + merge 脚本的 dedup 记录
- `warnings` 合并来自两侧 + merge 脚本的 lint 记录
- `content_mode` / `section_scan` 由 Reader VM 透传到合并产物，仅用于 QA / debug，不进入日报渲染

**tier = others 的 cluster 不调用 Value-Mapper**，但仍必须中文化。主 Agent 在 Writer 前生成 `${RUN_DIR}/others_translated.json`，为每个 `tier=others` cluster 提供 `title_zh` 与 `gist_zh`。Writer 渲染「其他信息」时不得直接显示英文 raw gist。VM 只处理 must_read / recommended / optional 三档。

---

## 3 · 去重合并规则（merge_perspectives.py § merge_single）

1. Audience VM prompt 内已做**第一道 dedup**（见 `value-mapper-audience.md §3 Dedup 硬契约`）
2. `merge_perspectives.py` 做**第二道 dedup 终审**：
   - 对每对 `(reader_block, audience_block)` 计算 body 的 Jaccard 相似度（中文 bigram + ASCII 词）
   - `>= --dedup-threshold`（默认 0.72）→ **drop audience_block**
   - 记录到 `skipped_perspectives`，字段名为中文：`{"视角": "audience · 角色/流程变化", "原因": "与 Reader「决策影响」内容高度重合（相似度 0.83）"}`
3. **日报不显示被 drop 的块**、也不显示"已略过 X 条"提示（中间 JSON 的 `skipped_perspectives` 仅供 debug / log）

---

## 4 · 降级（Agent 内部输出行为）

### 4.1 Reader VM

| 场景 | 行为 |
|---|---|
| 原文 `full_content` < 200 字 | core_content 数量可降到 2 条；`warnings` 记 `too_sparse` |
| 原文抓取失败 | core_content 第一条标注"原文抓取失败（{error_hint}）..."；value_blocks 降为 1 块；`warnings` 记 `fetch_failed` |
| 无 angle 命中 | `value_blocks: []` + `skipped_perspectives: [{"视角": "reader", "原因": "..."}]` |
| 输入 token degraded | 透传 warnings；对应 core_content 条末尾标注"（基于压缩摘要，细节可能遗漏）" |
| `content_mode = roundup_digest` | 必须输出 `section_scan`；`core_content` 第一条说明这是多主题聚合以及本日报选取的主线 |

### 4.2 Audience VM

| 场景 | 行为 |
|---|---|
| 全部候选 block 与 Reader 重复 | `value_blocks: []`；`skipped_perspectives: [{"视角": "audience", "原因": "与 Reader 视角全部重合"}]` |
| 内容过于专业且无法翻译给目标受众 | `value_blocks: []`；`skipped_perspectives: [{"视角": "audience", "原因": "无法形成目标受众可用启发"}]`；`pillars: []` |
| Reader 产物缺失 | `value_blocks: []`；`skipped_perspectives: [{"视角": "audience", "原因": "Reader VM 产物缺失"}]` |
| 抓取失败 | value_blocks 降为 1 块或空；`warnings` 记 `fetch_failed` |

### 4.3 merge_perspectives.py

| 场景 | 行为 |
|---|---|
| 某 cluster 缺 Reader VM 产物 | 全局 warning `missing_reader_vm`；该 cluster 不入 entries |
| 某 cluster 缺 Audience VM 产物（但 `--audience-dir` 启用） | 全局 warning `missing_audience_vm`；仍按仅 Reader 合并 |
| block lint 不通过 | drop 该 block + 入 `entries[].warnings[].type="lint_fail"` |

Pipeline 层编排降级（重试 / 超时中止 / VM 全失败处理）见 `../ARCHITECTURE.md §5`。

---

## 5 · 输入打包规则（`full_content` vs `compressed_summary`）

主 Agent 打包时自动判定（对 Reader VM 与 Audience VM 同规则）：

| 条件 | 处理 |
|---|---|
| `primary.full_content_tokens + Σ members[].full_content_tokens ≤ 18000` | 全传 `full_content` |
| 超阈值 | primary 保留 `full_content`；members 降级传 `compressed_summary`；warning 标注 |
| `primary.full_content_tokens > 18000`（极端长 transcript） | primary 也降级；warning `degraded: primary_compressed` |

**关键原则**：Fetcher 永远不做有损摘要然后丢弃原文。`compressed_summary` 仅作总输入超阈值时的降级材料。

---

## 6 · 质量校验（主 Agent 侧 + merge 脚本）

每个 `${RUN_DIR}/value_mapped_reader/{cid}.json` 和 `${RUN_DIR}/value_mapped_audience/{cid}.json` 写入后，主 Agent 做以下 lint：

- Schema 合法（所有必填字段存在、类型正确）
- `meta.cluster_id` 与输入一致
- `value_blocks[].angle` 在对应 perspective 的枚举集合内
- `value_blocks[].body` 40-110 中文字；禁用词黑名单（见 `../ARCHITECTURE.md §4 不变量 #7`）
- Reader VM：不得出现 `pillars` / `perspective=audience` block
- Audience VM：不得出现 base 字段 / `perspective=reader` block
- `core_content[]` 至少 1 条包含阿拉伯数字（或"首次 / 正式 GA / v3.0"等版本标识）—— 仅 Reader VM
- `title_zh` 不含英文直译痕迹 —— 仅 Reader VM
- Reader VM：`content_mode` 必填，且必须属于枚举集
- Reader VM：`content_mode = roundup_digest` 时，`section_scan` 至少 3 条、至少 1 条 `selection_decision = "selected"`，且 `core_content[0]` 必须说明"多主题聚合 / 本日报选取主线"
- Reader VM：`content_mode = roundup_digest` 时，`core_content[]` 不应出现"摘要提到"；若信息来自全文，应写"正文在 X section 中..."或"该 issue 将...归入..."

Lint 失败：**单 Agent 输出重试 1 次，仍失败则标记该 cluster 为 `degraded` 并保留已有输出**（不回退整个 Pipeline）。

merge 脚本内嵌二次 lint（见 `scripts/merge_perspectives.py`），不通过的 block 直接 drop 并写入 `warnings`。
