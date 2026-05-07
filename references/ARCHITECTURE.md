# 日报架构（ARCHITECTURE）

> 本文只保留 Pipeline 全景、数据契约接力、设计决策、关键不变量、Prompt caching 策略。
> Schema 细节去各 `agents/*.md`；视角规则去 `perspectives/*.md`。

---

## 1 · 运行链路全景（6 步单遍 · Step 4 含 3 子步 · 每日 1 次）

```
Step 0  Run Dir + Cleanup     [Python]   tmp/YYYY-MM-DD/ + 删除 7 天前 dated run dirs
Step 1  Fetcher              [Python]   sources.md → tmp/YYYY-MM-DD/raw_items.jsonl
Step 2  Deduper              [Python]   SimHash + 标题相似度 → tmp/YYYY-MM-DD/clusters/{id}.json + clusters_index.json
Step 3  Scorer               [AI × 1]   PROFILE + scoring_profile + clusters_index → scored.json（tier 分档）
Step 4a Value-Mapper · Reader [AI × N]  PROFILE + sources + perspectives/reader.md + cluster → value_mapped_reader/{id}.json
Step 4b Value-Mapper · Audience [AI × N] PROFILE + sources + perspectives/audience.md + cluster + reader 产物
                                         → value_mapped_audience/{id}.json
Step 4c Merge                 [Python]   reader + audience + dedup → value_mapped.json
Step 5  Outlook-Curator       [AI × 1]   PROFILE + value_mapped.json → outlook.json
Step 6  Writer                [Python]   clusters + scored + value_mapped + outlook → YYYY-MM-DD.md
```

**wall-clock 预期**：8-18 分钟（瓶颈：Fetcher 网络 I/O + Step 4a + Step 4b 两轮并行池串行）。

**LLM 调用数**：`2×N + 2`（Reader × N + Audience × N + Scorer × 1 + Outlook × 1）。
相比 v0.9 的 `N + 2`，Step 4 的 LLM 调用翻倍；但 prompt caching 命中后，Audience VM 静态前缀（PROFILE + sources + perspectives/audience.md）稳定，对 input token 影响可控。若高级启用 content pillars，才额外加入 pillar_config。

---

## 2 · 数据契约接力

| Step | 读 | 写 | Schema 真相位置 |
|---|---|---|---|
| 0 Run Dir + Cleanup | `tmp/` | `tmp/YYYY-MM-DD/run_context.json`；删除 7 天前 dated run dirs | `scripts/cleanup_tmp.py` |
| 1 Fetcher | `sources.md` | `${RUN_DIR}/raw_items.jsonl` · `${RUN_DIR}/fetcher.log` | `agents/fetcher.md` |
| 2 Deduper | `${RUN_DIR}/raw_items.jsonl` | `${RUN_DIR}/clusters/{id}.json` · `${RUN_DIR}/clusters_index.json` | `scripts/dedupe.py::cluster_index_row`（源代码即契约） |
| 3 Scorer | `PROFILE.md` · `references/scoring_profile.json` · `${RUN_DIR}/clusters_index.json` | `${RUN_DIR}/scored.json` | `agents/scorer.md §5` Prompt「对每个 cluster 产出」段 |
| 4a Reader VM | `PROFILE.md` · `sources.md` · `perspectives/reader.md` · `${RUN_DIR}/clusters/{id}.json` + scored 切片 | `${RUN_DIR}/value_mapped_reader/{id}.json` | `agents/value-mapper-schema.md §1.1 / §2.1` |
| 4b Audience VM | `PROFILE.md` · `sources.md` · `perspectives/audience.md` · `${RUN_DIR}/clusters/{id}.json` · `${RUN_DIR}/value_mapped_reader/{id}.json` | `${RUN_DIR}/value_mapped_audience/{id}.json` | `agents/value-mapper-schema.md §1.2 / §2.2` |
| 4c Merge | `${RUN_DIR}/value_mapped_reader/*.json` · `${RUN_DIR}/value_mapped_audience/*.json` · `${RUN_DIR}/scored.json` | `${RUN_DIR}/value_mapped.json` | `agents/value-mapper-schema.md §1.3 / §2.3` |
| 5 Outlook-Curator | `PROFILE.md` · `${RUN_DIR}/value_mapped.json` | `${RUN_DIR}/outlook.json` | `agents/outlook-curator.md` |
| 6 Writer | 上述全部 + `${RUN_DIR}/*.log` + `${RUN_DIR}/run_context.json` | `./outputs/daily-brief/YYYY-MM-DD.md` · `./outputs/daily-brief/YYYY-MM-DD.html` | `assets/daily.md.j2` · `assets/daily.html.j2`（模板即契约） |

**硬性原则**：任何下游 Step 只读同名或上游写入的文件；禁止跨 Step 共享内存状态。所有 Agent 间通信走文件。

**tmp 保留策略**：中间产物按 `tmp/YYYY-MM-DD/` 分日存放。每次运行 Step 0 调 `scripts/cleanup_tmp.py --retention-days 7`，只删除目录名符合 `YYYY-MM-DD` 且早于保留窗口的 run dir；非日期目录不动。长期资产只保留在 `outputs/daily-brief/YYYY-MM-DD.md` 与 `outputs/daily-brief/YYYY-MM-DD.html`。

---

## 3 · 设计决策（为什么运行链路这样设计）

### 3.1 为什么 `daily_outlook` 独立为 Outlook-Curator

- Value-Mapper 单 cluster 视角，看不到全局，无法跨条目综合
- 让 VM 背负 outlook 会挤压单条 value_blocks 质量预算
- outlook 本质是跨条目降噪（N 条高分中选 3-5 条结构性主线），天然适合独立 context window

### 3.2 为什么 Value-Mapper 是"单 cluster 并行池"而非批处理

- 单 cluster 输入 ~10-20K tokens，远低于 200K 上下文；批处理多 cluster 则 token 不可控
- 进程隔离：一条 cluster 出错不污染其他
- 并发池（上限 8）把 N 条缩成 ~N/8 的挂钟时间

### 3.3 为什么 Fetcher 不做"有损摘要"

- 早期压缩会丢 VM 需要的原始数字 / 机制 → `full_content` 永远保留
- `compressed_summary` 仅作"总输入超阈值"的降级备份
- Fetcher 不读 PROFILE，不做价值判断，职责只抓取

### 3.4 为什么 Writer 是 Python 模板而非 AI

- 报告渲染是纯结构化映射，AI 会乱发挥 / 说车轱辘话
- Jinja2 模板 100% 确定性
- Writer 失败不消耗 API token

### 3.5 为什么 Scorer 读全 PROFILE

- 简化画像会丢读者身份、目标受众关切、输出用途与风格等价值判断背景
- PROFILE ~1.5K + Scorer §3.0 P1/P2/P3 ~0.5K + clusters_index ~5K ≈ 7-8K 输入，远低于上下文上限

### 3.6 为什么 Step 4 拆 Reader VM + Audience VM（v0.10 新增）

**根因**：v0.9 前 Value-Mapper 把"对读者自己"和"对目标受众"两视角塞进一个 context。VM prompt 出现主语冲突（"你" vs "企业"）、禁用词相互矛盾、价值维度池两层并存导致 LLM 为凑答拼接。

**解法**：**prompt as architecture** — 每视角 = 一个独立 Agent。

- **Reader VM（Step 4a）** 产 base 字段（title_zh / key_tags / core_content / reading_suggestion）+ Reader 视角 value_blocks。Base 字段下游共享——fork 用户即便不跑 Audience VM，也能拿到一份完整日报。
- **Audience VM（Step 4b）** 产 Audience 视角 value_blocks。Audience VM 是可选扩展；fork 用户若只服务自己可跳过。Content pillars 是高级 opt-in 扩展，不是默认路径。
- **Merge（Step 4c）** 做字段归并 + dedup 二次终审 + Lint 终审；纯 Python 无 AI，100% 确定性。

**权衡**：
- LLM 调用 N+2 → 2N+2（成本上升，但 prompt cache 命中后 < 15% 输入 token 上升）
- 挂钟时间：Step 4a 与 4b 串行（因 4b 需要 4a 产物做 dedup），总时长约增加 30-50%
- 复杂度：Pipeline 步骤 6 → 8（4a/4b/4c 拆分）；但每步职责更纯、错误隔离更好

**可扩展性**：新增视角 = 新建 `perspectives/{name}.md` + `agents/value-mapper-{name}.md`；SKILL.md Step 4 并行池加 4b' 子步；merge 脚本添加该 VM 的过滤逻辑。**不改任何现有文件**。

---

## 4 · 关键不变量

1. 所有 Agent 间通信只走**文件**；主 Agent 不传递内存对象
2. 任何 Agent 写文件前必须**先写 `.tmp` 再 rename**（原子性）
3. Value-Mapper 只看单 cluster；禁止跨 cluster 综合（综合归 Outlook-Curator）
4. Scorer 不碰 `full_content`；只读 `clusters_index.json`
5. Fetcher 不碰 `PROFILE.md`；价值判断下沉到 Scorer / Value-Mapper
6. Writer 不调 AI；全本地渲染
7. 禁用词黑名单（"值得关注"、"意义重大"、"反思了"、"做出了重大"、"具有深远"、"十分重要"、"带来了根本性"）在 Reader VM / Audience VM / Outlook-Curator 必须 lint
8. **视角独立性（v0.10 新增）**：Reader VM 与 Audience VM 的 context 彼此不可见——Reader 不知道 Audience 存在；Audience 读 Reader 产物但只做 dedup，不改写 Reader 任何字段
9. **Content pillars optional**：默认不产出、不渲染 pillars；只有 `features.pillar_mapping=true` 时，Pillar 才由 Audience VM 产出。Reader VM 不输出 pillars
10. **Perspective 字段强制（v0.10 新增）**：所有 `value_blocks[]` 必须有 `perspective ∈ {"reader", "audience"}` + `angle`（对应视角枚举集的 key）；日报渲染按 perspective 分组
11. **Prompt hygiene**：配置、示例、反馈和稳定运行的提示词边界见 `references/prompt_hygiene.md`；不得把 demo 示例当用户画像，不得把内部 ID / lint key / raw path 渲染给用户
12. **配置落盘优先**：评分规则只从 `scoring_profile.json` 注入 Scorer；价值视角枚举和中文标签只从 `angle_config.json` 注入 merge/render；stable 每日运行不得依赖聊天记忆。

---

## 5 · 降级矩阵

| 场景 | Step | 行为 |
|---|---|---|
| 信源抓取失败 | 1 | 跳过该信源；`${RUN_DIR}/failures.log` 记录；Writer 阶段显示健康告警 |
| 单条内容 < 200 字 | 1 | 仍产出，标记 `too_sparse`；Reader VM 降级为少条 core_content |
| 长 transcript > 18K tokens | 1 | primary 保留 full_content；members 降级 compressed_summary |
| 长 transcript > 主限 | 1 | primary 也 fallback；warning `degraded: primary_compressed` |
| Scorer JSON 不合法 | 3 | 重试 1 次；仍失败则全档降为 `optional`，Writer 显示降级提示 |
| 单 cluster Reader VM 超时 / Lint fail | 4a | 重试 1 次；仍失败则该 cluster 标 `degraded`；Step 4b 见到 Reader 缺失时该 cluster 按「仅 Reader 模式」（Audience 空）处理 |
| 单 cluster Audience VM 超时 / Lint fail | 4b | 重试 1 次；仍失败则该 cluster 标 `audience_degraded`；merge 按「仅 Reader 模式」处理 |
| Reader VM 全部失败 | 4a | 中止 Pipeline；Writer 只渲染「信源状态」+「其他信息」+ 告警段 |
| Audience VM 全部失败 | 4b | 继续 Pipeline；merge 按「仅 Reader 模式」；Writer 不渲染 Audience value |
| merge 脚本 lint 有 block fail | 4c | drop 该 block + 记 warning；不回退 Pipeline |
| Outlook-Curator 失败 | 5 | 重试 1 次；仍失败则 `daily_outlook=[]`；Writer 省略「今日格局」段并提示 |
| Writer 模板错误 | 6 | Python 抛异常；主 Agent 降级产出 `YYYY-MM-DD-DRAFT.md`（原始堆叠） |

---

## 6 · Prompt caching 策略（Step 4a + 4b VM 并行池各自独立）

### 6.1 静态前缀

Reader VM 静态前缀（N 条调用间完全相同）：

| 组成 | 来源 | 量级 |
|---|---|---|
| Reader VM system prompt | `agents/value-mapper-reader.md §3` | ~4K |
| 读者画像 | `PROFILE.md` | ~3K |
| 信源注册表 | `sources.md` | ~10-14K |
| Reader 视角规则 | `perspectives/reader.md` | ~1.5K |

Reader 前缀 ~18-22K tokens。

Audience VM 静态前缀（N 条调用间完全相同；与 Reader 前缀独立成 cache）：

| 组成 | 来源 | 量级 |
|---|---|---|
| Audience VM system prompt | `agents/value-mapper-audience.md §3` | ~4K |
| 读者画像 | `PROFILE.md` | ~3K |
| 信源注册表 | `sources.md` | ~10-14K |
| Audience 视角规则 | `perspectives/audience.md` | ~2K |
| Content pillars optional config | `pillar_config.json` | ~0.5K，仅 opt-in |

Audience 前缀 ~19-23K tokens。

### 6.2 实现契约

宿主支持 prompt cache 时，主 Agent 构造每次 VM 子调用，在各自 `system_prompt` 的**最后一个** content block 附加：

```json
{"cache_control": {"type": "ephemeral"}}
```

TTL 5 分钟。Reader 与 Audience 的 cache 命名空间独立，互不影响。宿主不支持 `cache_control` 时直接跳过；这只影响成本，不影响输出正确性。

### 6.3 预期收益（N=25-30 的典型日）

| 场景 | input token 成本（相对基础输入） |
|---|---|
| Reader VM 首次调用（写 cache） | ~1.25× |
| Reader VM 后续 N-1 次（读 cache） | ~0.1× |
| Audience VM 首次调用（写 cache） | ~1.25× |
| Audience VM 后续 N-1 次（读 cache） | ~0.1× |

N=25-30 条的典型日：总输入 token ~300K → ~100K（**~60-70% 下降**，与 v0.9 的 cache 收益相当）。

### 6.4 失效条件

- `PROFILE.md` / `sources.md` / 各 perspective md / 对应 VM prompt 任一字节变化 → 该 VM 的 cache miss；启用 content pillars 时，`pillar_config.json` 变化也会造成 Audience VM cache miss
- Reader 或 Audience 的 cache 独立；一个 miss 不影响另一个
- 5 分钟 TTL 内无后续请求读到 → 自然过期
- 平台封装层未透传 `cache_control` → 自动 fallback（不影响正确性，仅失成本优势）

---

## 7 · 目录布局

```
outputs/rss-daily-brief/
├── SKILL.md                # 主 Agent 入口（orchestrator 步骤）
├── references/
│   ├── ARCHITECTURE.md     # 本文件
│   ├── PROFILE.md          # 读者画像
│   ├── sources.md          # 信源注册表
│   ├── EXAMPLE.md          # 期望输出示范
│   ├── pillar_config.json  # Optional content pillar extension（key + display names + trigger tags）
│   ├── perspectives/       # 视角规则（每视角一文件）
│   │   ├── reader.md       # Reader 视角 · Angle 池 · 主语 · 禁用词
│   │   └── audience.md     # Audience 视角 · Angle 池 · Dedup 契约
│   └── agents/             # 子 Agent Prompt + Schema + Lint
│       ├── fetcher.md
│       ├── scorer.md              # 职责 / Tier / System Prompt 包装段 / Lint
│       ├── scorer-rubric.md       # P1/P2/P3 + base_score + bonus + 水文
│       ├── value-mapper-reader.md   # Reader VM · 职责 / 调用约定 / Prompt 包装段 / 降级
│       ├── value-mapper-audience.md # Audience VM · 同上
│       ├── value-mapper-schema.md   # 双 VM 输出契约 + Schema + merge 规则 + Lint
│       ├── outlook-curator.md
│       └── writer.md
├── scripts/                # Python 实现
│   ├── fetch.py · dedupe.py · render.py · healthcheck.py
│   ├── merge_perspectives.py  # Step 4c · 合并 Reader + Audience + dedup + lint
│   ├── archive_adapters.py · bootstrap.sh
├── assets/
│   ├── daily.md.j2         # Writer Markdown Jinja2 模板（双视角分组渲染）
│   └── daily.html.j2       # Writer HTML Jinja2 模板（暗色日报版式）
├── tmp/                    # Pipeline 中间产物（dated run dirs）
│   └── YYYY-MM-DD/
│       ├── run_context.json
│       ├── raw_items.jsonl · fetcher.log · .fetcher_state.json
│       ├── clusters/ · clusters_index.json
│       ├── scored.json
│       ├── value_mapped_reader/   # Step 4a 产物
│       ├── value_mapped_audience/ # Step 4b 产物
│       ├── value_mapped.json      # Step 4c 合并产物
│       └── outlook.json
└── outputs/daily-brief/
    ├── YYYY-MM-DD.md       # 每日 Markdown 产物
    └── YYYY-MM-DD.html     # 每日 HTML 产物
```

---

## 8 · 运行期模型约束

| 角色 | 模型 | 切换方式 |
|---|---|---|
| 主 Agent | 宿主当前会话模型 | 用户或宿主设置 |
| 子 Agent（Scorer / Reader VM / Audience VM / Outlook-Curator） | 宿主默认高质量文本模型；若无子 Agent 能力则由主 Agent 顺序模拟 | 按宿主能力决定 |

多模型对比只能由用户用不同主 Agent 跑同一数据得到。
