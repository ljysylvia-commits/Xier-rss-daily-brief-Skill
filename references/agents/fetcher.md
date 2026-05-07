# Fetcher（Python, 无 AI）

**角色代号**：`fetcher`
**调用方**：主 Agent 在 Pipeline Step 1 通过 Bash 调 `scripts/fetch.py`
**输入**：`../sources.md`
**输出**：`${RUN_DIR}/raw_items.jsonl`（逐行 JSON）+ `${RUN_DIR}/fetcher.log`

---

## 1 · 职责

并发抓取 `sources.md` 里所有信源过去 `coverage_window_hours` 内的新条目，输出扁平化的 `raw_items.jsonl`。**不做价值判断、不压缩、不去重**。

---

## 2 · full_content 产出规则

| 来源类型 | `full_content` |
|---|---|
| RSS 全文（`<content:encoded>`） | RSS 原文 |
| RSS 摘要（仅 `<description>`）+ 网页补全 | Readability 抽取的正文 |
| 播客（仅 show notes） | show notes 原文 |
| 播客（有 transcript） | 完整 transcript |
| GitHub README / 工程博客 | 完整正文 |
| 抓取失败 | `null`（`fetch_status` 标注具体错误类型）|

**硬性原则**：Fetcher **永远不做有损摘要**。原文永远落 `full_content`。

### `compressed_summary` 字段契约

`raw_items.jsonl` 每行均有 `compressed_summary` 字段，Fetcher 阶段**恒为 `null`**（占位保持 schema 稳定，下游读取无需分支判断）。Fetcher 是纯 Python，不调模型。当主 Agent 在 Step 4 打包 VM 输入时发现 `primary.full_content_tokens + Σ members[].full_content_tokens > 18000`，对 members 做一次轻量压缩（见 `value-mapper-schema.md §5 输入打包规则`），压缩文本作为临时变量写入传给 VM 的单 cluster JSON，**不回写** `raw_items.jsonl`。

---

## 3 · 输出 Schema（`raw_items.jsonl` 每行）

```json
{
  "item_id": "src:<source_id>:<sha1(url)[:8]>",
  "source_id": "demo_public_source",
  "source_name": "Demo Public Source",
  "source_url": "https://example.org/story",
  "original_title": "New public data changes planning priorities",
  "published_at": "2026-04-26T14:30:00+00:00",
  "fetched_at": "2026-04-26T07:05:12+08:00",
  "lang": "en",
  "content_type": "blog_post",
  "full_content": "...",
  "full_content_tokens": 3200,
  "compressed_summary": null,
  "fetch_status": "ok",
  "fetch_error": null,
  "freshness_state": "fresh|stale|irregular"
}
```

### content_type 枚举

`blog_post` · `newsletter` · `podcast` · `github` · `video` · `news` · `research_paper` · `other`

### fetch_status 枚举

`ok` · `http_4xx` · `http_5xx` · `timeout` · `parse_error` · `blocked`

---

## 4 · 并发 / 网络行为

- 并发上限：20
- 单条超时：30s（HTTP）+ 10s（Readability 解析）
- 重试：网络类错误重试 2 次，指数退避（1s → 4s）
- UA：标准浏览器 UA（避免 bot 墙）；GitHub / Anthropic 等官方 API 用对应官方 UA
- 尊重 `robots.txt`

---

## 5 · 健康态（`freshness_state`）

| 值 | 判据 |
|---|---|
| `fresh` | 近 48h 有条目 |
| `stale` | 48h-7d 无新条目但 7d 内有过 |
| `irregular` | 7d-90d 无新条目 |
| `dead` | > 90d 无新条目（主 Agent 层面告警建议下线） |

freshness_state 写入每条 item 的同时，`${RUN_DIR}/fetcher.log` 汇总每个 source 的状态，供 Writer 渲染「信源状态」段。

---

## 6 · 失败处理

单信源失败不阻塞其他信源；超过 50% 信源失败则主 Agent 中止 Pipeline。完整降级矩阵见 `../ARCHITECTURE.md §5`。

---

## 7 · 参考

- 设计理由（为何不做有损摘要）：`../ARCHITECTURE.md §3.3`
- Python 实现：`../../scripts/fetch.py`
