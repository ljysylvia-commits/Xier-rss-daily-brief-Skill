# 运行模式

> 用途：决定当前应该走首次配置、调优，还是稳定日报运行。不是每个步骤都每天执行。

## 模式表

| 模式 | 使用场景 | 执行步骤 |
|---|---|---|
| `setup` | 首次配置用户，或 demo 文件仍需替换 | Step -2、Step -1，然后 Step 0-6（包含 Step 4d） |
| `tuning` | 用户 review 后要求调整评分、信源、价值视角或视觉样式 | Step 7，然后重跑 Step 0-6（包含 Step 4d） |
| `stable` | 配置已确认，日报应每日运行 | 只跑 Step 0-6（包含 Step 4d） |

## Setup 模式

当用户尚未确认自己的画像、价值视角、信源和日报偏好时使用。

1. Step -2 第一轮：推导并确认读者画像、P1/P2/P3 评分规则、降权/加权规则和 reader value angles。
2. 写入 `PROFILE.md`、`references/scoring_profile.json`、`references/angle_config.json`、`perspectives/reader.md`。
3. Step -2 第二轮：确认是否有目标受众；有则写入 `perspectives/audience.md` 和 audience angles，无则关闭 `features.audience_view`。
4. Step -1：推荐或确认 sources，让用户增删信源。
5. 确认日报格式、长度和 HTML 主题。默认输出 Markdown + HTML；长度为 must 3 / recommended 5 / optional 10；HTML 主题二选一：`light` 或 `dark`。
6. 运行 healthcheck 和一次短 dry run。
7. 渲染日报，请用户 review。

## Tuning 模式

当用户对输出提出反馈时使用。

1. 读取 `feedback_loop.md`。
2. 把反馈转成具体文件修改方案。
3. 在应用持久化配置 / 模板改动前，请用户确认。
4. 应用确认后的改动。
5. 重渲染同一次 run 或 fixture。
6. 用户确认前保持 `feedback.status = "tuning"`。

## Stable 模式

当 `config/report_config.json.feedback.status = "stable"` 且 `automation.enabled = true` 时使用。

stable 每日运行不应重复 Step -2、Step -1、Step 7 或 Step 8，除非配置变化或用户给出新反馈。

每日运行路径：

1. Step 0：准备运行目录并清理旧 tmp。
2. Step 1：抓取信源。
3. Step 2：去重。
4. Step 3：评分并运行 deterministic guardrail。
5. Step 4：价值映射。
6. Step 4d：生成 Final Other Signals 中文摘要。
7. Step 5：生成今日判断。
8. Step 6：渲染输出。

`Step 3b 翻译 Others` 已由 `Step 4d Final Others 中文摘要` 替换；二者不并存。

如果输出质量漂移，或用户给出新反馈，切回 `tuning`。

## 约束

- 用户未 review 至少一份生成日报前，不要标记 `stable`。
- 没有展示修改方案并获得用户确认前，不要应用 feedback-loop 改动。
- stable 每日运行不能依赖聊天记忆；偏好必须落到文件。
- 每日自动化中不要重新做 source onboarding，除非 `sources.md` 缺失或用户明确要求修改信源。
