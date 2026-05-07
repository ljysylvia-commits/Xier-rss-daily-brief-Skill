# Writer（Python 模板, 无 AI）

**角色代号**：`writer`
**调用方**：主 Agent 在 Pipeline Step 6 通过 Bash 调 `scripts/render.py`
**输入**：`${RUN_DIR}/clusters_index.json` · `scored.json` · `value_mapped.json` · `outlook.json` · `others_translated.json` · `fetcher.log`（信源状态）· `run_context.json`
**输出**：`./outputs/daily-brief/YYYY-MM-DD.md` · `./outputs/daily-brief/YYYY-MM-DD.html`

---

## 1 · 职责

纯结构化渲染。读入 Pipeline 的全部 JSON 产物，套用 Jinja2 模板渲染成 `EXAMPLE.md` 所示格式的 Markdown，并同步输出同内容的 HTML 版本。**不调 AI、不做价值判断、不改写内容**。

「其他信息」表格必须使用 `others_translated.json` 的中文标题与中文内容重点；缺失时应由主 Agent 先补齐，不应把英文原文截断文本直接渲染给用户。

渲染区块、Badge 规则、可选 content pillar key → 中文映射等**全部由模板承载**，模板即契约：

- Markdown 模板：`../../assets/daily.md.j2`
- HTML 模板：`../../assets/daily.html.j2`
- 样例：`../EXAMPLE.md`
- Python 实现：`../../scripts/render.py`

---

## 2 · 文件名与覆盖策略

- 主产物：`YYYY-MM-DD.md` 和 `YYYY-MM-DD.html`
- 重跑：覆盖同名文件（用户自行管理历史；Writer 不做版本保留）
- 若存在 `YYYY-MM-DD.md` 且本次是重跑，Writer 在 Markdown 首行加 `<!-- regenerated at HH:MM -->` 注释；HTML 在 masthead 标记 regenerated 时间

---

## 3 · 降级（Agent 内部）

Writer 只负责排版，不做二次内容校验（禁用词 lint 在 VM / Outlook-Curator 侧完成）。常见降级信号：

- `outlook.json` 的 `daily_outlook=[]` → 省略「今日格局」段并加注释
- `scored.json` 为空 → 只输出「⚠️ Pipeline 降级」提示
- 单 cluster `value_mapped` 标记 `degraded` → 条目末尾追加降级提示

Pipeline 层编排降级（模板错误时 DRAFT fallback）见 `../ARCHITECTURE.md §5`。

---

## 4 · 参考

- 设计理由（为何是 Python 模板而非 AI）：`../ARCHITECTURE.md §3.4`
- 模板即渲染契约：`../../assets/daily.md.j2` · `../../assets/daily.html.j2`
- 样例校准锚点：`../EXAMPLE.md`
