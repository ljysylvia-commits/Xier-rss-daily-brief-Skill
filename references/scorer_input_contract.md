# Scorer 输入字段扩展实施合同

## 目标

让 Step 3 Scorer 在不读取完整正文的前提下，获得比标题更稳定的轻量证据，用于降低标题党、RSS 标题/正文不一致、低信息密度和误分档风险。

本合同新增两个字段：

| 字段 | 写入位置 | 来源 | 用途 |
|---|---|---|---|
| `rss_summary` | `raw_items.jsonl`、`clusters/{id}.json`、`clusters_index.json` | RSS / Atom entry 的 `summary` 或 `description` 清洗文本 | 给 Scorer 看 feed 原始摘要；不是模型摘要 |
| `content_excerpt` | `clusters_index.json` | `primary.full_content` 清洗后截取前 500 字符 | 给 Scorer 看正文开头证据；不是全文 |
| `primary_tokens` | `clusters_index.json` | primary item 的 `full_content_tokens` | 判断正文证据是否存在 |
| `fetch_status` | `raw_items.jsonl`、`clusters/{id}.json`、`clusters_index.json` | Fetcher 状态 | 识别正文抽取失败 |
| `detail_fetch_status` | `raw_items.jsonl`、`clusters/{id}.json`、`clusters_index.json` | 详情页状态 | 区分 HTTP / parse / blocked |
| `evidence_state` | `clusters_index.json` | Deduper 透传 primary item 证据状态 | 给 Scorer 与 guardrail 做证据可用性判断 |
| `content_warning` | `clusters_index.json` | Fetcher 内容抽取 warning | 保留低质量抽取原因 |

## 数据流

1. Fetcher 在 `fetch_rss()` 中读取 RSS / Atom entry：
   - `summary_html = entry.get("summary") or entry.get("description") or ""`
   - 清洗 HTML 后得到 `summary_text`
   - 写入 `RawItem.rss_summary`
2. Fetcher 对非 RSS 路径写入 `rss_summary = null`，保持 schema 稳定。
3. Deduper 保存完整 cluster 时不做额外处理，`rss_summary` 会随 raw item 保留在 `primary` / `members` 中。
4. Deduper 写 `clusters_index.json` 时：
   - `rss_summary = primary.rss_summary`，最长保留 800 字符
   - `content_excerpt = primary.full_content`，最长保留 500 字符
   - 透传 `primary_tokens`、`fetch_status`、`detail_fetch_status`、`evidence_state`、`content_warning`
5. Scorer 读取 `clusters_index.json` 时，可以使用 `rss_summary`、`content_excerpt` 和证据状态字段辅助判断，但仍不得声称读过完整正文。
6. Scorer 输出后，主 Agent 运行 `scripts/apply_scoring_guardrails.py`。当 `primary_tokens=0`、`rss_summary=null`、`fetch_status=content_extraction_failed` 三项同时成立时，强制 `tier=others`。

## Scorer 边界

Scorer 可以用新增字段判断：

- 标题是否与摘要/正文开头明显不一致
- 内容是否包含具体机制、数字、案例、约束、方法论线索
- 是否疑似营销、水文、低信息密度
- P1/P2/P3 档位是否需要上调或下调

Scorer 不可以用新增字段做：

- 全文级结论
- 复杂论证链总结
- 对正文后半部分的事实断言
- Reader / Audience 价值翻译

完整正文仍然只进入 Value-Mapper 阶段。

## 兼容性

- 旧 `raw_items.jsonl` 没有 `rss_summary` 时，Deduper 使用 `null`，不报错。
- 新 `clusters_index.json` 只是增加字段，`render.py` 和 `merge_perspectives.py` 会忽略未使用字段。
- `content_excerpt` 和 `rss_summary` 只来自 primary item，不汇总 members，避免 Scorer 输入膨胀。
- `rss_summary = null` 本身不触发降级；很多非 RSS、播客或摘要缺失源仍可能有 `content_excerpt` 或 `full_content`。

## 验证步骤

1. 用旧 `raw_items.jsonl` 跑 `scripts/dedupe.py`，确认兼容旧数据。
2. 用最小 RSS fixture 跑 `scripts/fetch.py`，确认 `raw_items.jsonl` 写入 `rss_summary`。
3. 跑 `scripts/dedupe.py`，确认 `clusters_index.json` 写入 `rss_summary` 和 `content_excerpt`。
4. 跑 `scripts/apply_scoring_guardrails.py`，确认无正文证据条目固定进入 `others`，有 `rss_summary` 的短内容不被误降级。
5. 跑 `python3 scripts/run_contract_tests.py`。
6. 跑 `python3 -m py_compile scripts/fetch.py scripts/dedupe.py scripts/render.py scripts/merge_perspectives.py scripts/apply_scoring_guardrails.py scripts/build_other_signal_inputs.py scripts/run_contract_tests.py`。
7. 跑 `python3 scripts/healthcheck.py --root .`。
