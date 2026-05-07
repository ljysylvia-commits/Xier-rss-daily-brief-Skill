# 用户反馈闭环

> 用途：用户看完日报后，如果反馈“太技术了”“这个应降权”“我更想看政策影响”“HTML 字体太浅”等问题，用本文件把反馈转成可持久化配置，而不是只留在聊天里。

## 目标

把用户反馈沉淀到配置、评分规则、信源或模板文件中，让下一次日报能复现同样偏好。

## 反馈路由

| 用户反馈 | 修改目标 | 修改内容 |
|---|---|---|
| “这个应该降权” | `references/scoring_profile.json` | 增加 `demotion_rules`、弱主题类别、信源惩罚或 spam 判据 |
| “这个应该是必读” | `references/scoring_profile.json` | 增加 P1 主题 / 证据规则或权威信源提示 |
| “太技术了” | `references/angle_config.json`、`perspectives/reader.md`、`perspectives/audience.md`、`config/report_config.json.labels` | 调整价值角度，减少技术细节，改成更业务或读者友好的表达 |
| “我更想看政策 / 成本 / 风险 / 研究影响” | `references/scoring_profile.json`、`references/angle_config.json`、`perspectives/*.md`、`outlook.style` | 增加优先视角和今日判断重点 |
| “这个信源太吵” | `sources.md`、`references/scoring_profile.json` | 标记为 broad discovery / probe，或移除 |
| “这个模块没用” | `report_config.json.features`、模板文件 | 关闭 audience view、pillar mapping，或调整模板区块 |
| “HTML 字体太浅 / 看不清” | `assets/daily.html.j2`、`report_config.json.html` | 提高对比度、字号、行高、间距，或切换主题 |
| “我只要 Markdown / HTML” | `report_config.json.outputs.formats` | 修改输出格式 |
| “日报太长” | `references/scoring_profile.json`、`config/report_config.json`、模板文件 | 调整 `report_length` 或提高入选阈值；默认 must 3 / recommended 5 / optional 10，其余进入其他信息 |

## 修改流程

1. 把用户反馈复述成一个具体配置修改方案。
2. 指出要改的文件。
3. 在编辑配置、评分规则、信源或模板前，请用户确认这个持久化改动；只允许已确认反馈写入稳定配置。
4. 应用已确认的改动。
5. 重渲染同一 fixture 或最近一次 run。
6. 用具体检查验证变化生效。
7. 用户确认效果后，将 `config/report_config.json.feedback.status` 标记为 `stable`。

## 自动化门槛

满足以下条件前，不建议进入每日自动化：

- 用户画像、`scoring_profile.json`、reader value angles 和可选 audience angles 已确认。
- 信源列表通过 fetch / probe smoke test。
- 用户至少 review 过一份生成日报。
- 主要反馈项已经应用，或明确放入 deferred / open items。
- 输出格式和 HTML 主题稳定。

稳定后设置：

```json
"feedback": {
  "status": "stable",
  "last_reviewed_at": "YYYY-MM-DD",
  "open_items": []
}
```

如果仍有未解决问题，保持 `status = "tuning"`。

Step 7 和 Step 8 不属于普通每日运行，只在 setup、tuning 或用户给出新反馈时使用。

## 每日自动化说明

本 Skill 不直接创建调度器。配置稳定后，可由宿主环境通过 cron、task runner、CI 或 automation 功能每日运行同一条 pipeline。自动化应先运行 healthcheck，再渲染配置指定的输出格式。
