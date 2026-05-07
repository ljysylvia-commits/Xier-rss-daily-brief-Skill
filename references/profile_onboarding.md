# 用户画像配置

> 用途：把首次配置拆成少量可对齐的轮次。每一轮确认后立即写入对应文件，不等到最后一次性落盘。

## 目标

让用户逐步建立自己的信息判断系统：先确认读者画像和评分规则，再确认是否有目标受众，然后确认信源，最后确认日报结构和 HTML 风格。

不要把 demo profile、demo sources 或测试 fixture 当成真实用户默认值。

## 第一轮：读者画像 + 评分规则 + 读者价值视角

只对齐读者本人，不讨论目标受众和 HTML 样式。

需要确认：

- 读者是谁：角色、领域、当前目标、使用场景
- 为什么读：决策、研究、经营、学习、写作、团队同步等
- 高价值内容：P1 / P2 / P3 分别是什么
- 低价值内容：哪些内容要降权
- 加分信号：权威信源、一手数据、反共识、多信源确认、可执行细节等
- 读者价值视角：5-8 个 reader angle，每个 angle 需要 key、中文名和使用场景

确认后立即写入：

- `references/PROFILE.md`
- `references/scoring_profile.json`
- `references/perspectives/reader.md`
- `references/angle_config.json`

`scoring_profile.json` 必须包含用户确认的 P1 / P2 / P3、demotion rules、bonus rules 和 tier caps。Scorer 会读取这个文件。

## 第二轮：目标受众

只问一个核心问题：这份日报是否也会给别人看？

如果没有：

- 设置 `features.audience_view = false`
- 不生成 audience value blocks

如果有，继续确认：

- 目标受众是谁，例如团队、高管、客户、公众号 / 视频号读者、学生、社区成员
- 他们关心什么
- 他们不需要什么
- 表达应偏业务、技术、政策、研究、管理层还是大众解释
- 需要哪些 audience value angles

确认后立即写入：

- `references/perspectives/audience.md`
- `references/angle_config.json`
- `config/report_config.json.features.audience_view`
- `config/report_config.json.labels.audience_value`

## 第三轮：信源

基于前两轮配置推荐 starter source list，让用户增删确认。

推荐表至少包含：

| name | type | url_primary | why it fits | expected value | noise risk | stability level |
|---|---|---|---|---|---|---|

`stability level` 可选：

- `rss_stable`
- `archive_probe`
- `official_but_no_feed`
- `high_noise_broad_discovery`

确认后立即写入：

- `references/sources.md`

用户确认前，不要直接抓取。用户确认后，先运行 source probe；probe 通过不等于内容质量可用，archive source 仍需检查是否能发现文章级标题、链接和发布时间。

## 第四轮：日报格式

默认输出：

```json
["markdown", "html"]
```

先生成一份 demo Markdown 结构给用户确认，不需要先做完整 HTML。默认结构：

- 今日判断
- 必读
- 推荐
- 可选
- 其他信息
- 信源状态

默认长度配置：

```json
{
  "max_must_read": 3,
  "max_recommended": 5,
  "max_optional": 10,
  "show_other_table": true
}
```

含义：

- 最多 3 条 `must_read`
- 最多 5 条 `recommended`
- 其他值得读的内容进入 `optional`，最多 10 条
- 剩余全部进入 `others`

Markdown 结构确认后，再让用户二选一 HTML 风格：

- `light`：明亮版，适合白底文档、转发、打印、管理层扫读
- `dark`：黑夜版，适合屏幕沉浸阅读和高对比视觉

确认后写入：

- `config/report_config.json.outputs`
- `config/report_config.json.report_length`
- `config/report_config.json.html_theme`

## 不要做

- 不要第一轮一次性问完画像、目标受众、信源、格式、HTML 风格。
- 不要复用其他用户的私人偏好。
- 不要在用户没说的情况下写死 AI、SaaS、增长、创作者、咨询、工程等假设。
- 不要因为用户要日报就自动推断他有目标受众。
- 当 `features.audience_view = false` 时，不要生成 audience-facing value blocks。
- 不要把 demo 示例当成真实用户默认值。

## 第一轮草稿格式

```markdown
## 读者配置草稿

读者：
- 角色：
- 主题：
- 当前目标：

评分：
- P1：
- P2：
- P3：
- 降权：
- 加分：

读者价值视角：
- `angle_key`：显示名 —— 使用场景
```

## 第二轮草稿格式

```markdown
## 目标受众配置草稿

目标受众：
- 启用：true/false
- 受众：
- 他们关心：
- 他们不需要：

目标受众价值视角：
- `angle_key`：显示名 —— 使用场景
```
