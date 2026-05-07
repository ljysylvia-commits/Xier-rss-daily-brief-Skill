# 提示词卫生

> 用途：当修改 prompt、画像配置、反馈路由或每日自动运行行为时，用本文件避免 demo 泄漏、内部语言泄漏和规则漂移。

## 目标

- 保持 Skill 可配置，但不让 demo 示例变成用户默认值。
- 让 stable 每日运行保持短、确定、无 setup-only 问题。
- 防止私人画像泄漏、内部运行语言泄漏、过期假设和提示词堆叠。
- 在提升用户体验的同时保持输出质量。

## 运行规则

1. **按模式读取文件**
   - `setup` / `demo`：读取 onboarding 和 source recommendation 文档。
   - `tuning`：读取 feedback loop，以及反馈影响到的配置 / 模板文件。
   - `stable`：除非 healthcheck 失败，只读取 Step 0-6 必需的 pipeline prompts 和 config。

2. **Demo 不是身份**
   - demo profile、demo sources、fixture topics、example value angles 都是占位。
   - 不要推断新用户想要 demo topic、demo scoring logic、demo HTML style 或 demo source mix。
   - 用户专属配置缺失时，根据当前对话起草并让用户确认；确认后写入 `PROFILE.md`、`scoring_profile.json`、`angle_config.json`、`perspectives/*.md` 或 `config/report_config.json`。

3. **持久化修改前先确认**
   - “太技术了”“这个降权”“更多政策影响”“字体太浅”等反馈是 tuning signal。
   - 先提出具体 file-level 修改方案。
   - 用户确认后，再编辑 config、scoring、source、perspective 或 template 文件。
   - Step 7/8 这类 feedback/tuning 步骤只在用户给出反馈或 setup 阶段出现；stable 每日运行不得重复追问。

4. **替换、合并、删除**
   - 优先修改现有规则，不追加近似重复规则。
   - 用户确认画像替换 demo 后，删除过期 demo 表述。
   - 未解决冲突写入 `feedback.open_items`，不要藏在聊天记忆里。

5. **用户输出禁止内部语言**
   - 用户可见 Markdown 和 HTML 不得出现 cluster IDs、lint keys、warning enums、raw file paths 或 implementation labels。
   - 把失败转换成可理解中文，例如“内容深度受限”或“信源抓取失败”。
   - 如果报告需要比较条目，用标题或信源语义名称，不用 `c0007` 这类 ID。

6. **强制输出语言**
   - 报告里的摘要、标题、今日判断、value blocks 和低相关 rows 必须使用 `output_language`。
   - source names、product names、URLs 和必要术语可保留原文以保证准确。

7. **日期必须具体**
   - run metadata 和持久化配置使用 `2026-04-29` 这类具体日期。
   - 除渲染日报上下文外，避免在持久配置里写 “today”、“yesterday”、“recently”、“刚刚”。

8. **Angle keys 是契约**
   - 不要在 prompt 中随意新增 value angle keys，除非同时更新 perspective 文件、schema、merge logic、labels 和 tests。
   - 渲染标签要人类可读；raw keys 只用于 JSON。

9. **示例保持中性**
   - 示例使用通用公开信源场景，除非 test fixture 明确记录某个角色。
   - 不要把过去用户的私人画像、信源列表、价值语言或业务定位当成默认示例。

10. **打包前质量门槛**
    - 运行 `scripts/healthcheck.py --root .`。
    - 编译 Python scripts。
    - 确认 package 排除 `outputs/`、`tmp/`、`__pycache__/` 和 `.pyc`。
    - 抽查用户可见日报文本，确认可读且无内部语言泄漏。
