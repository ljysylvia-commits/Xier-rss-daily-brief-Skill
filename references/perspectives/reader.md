# 读者视角（Reader Perspective）

> 用途：定义 Reader value angle pool 和写作规则。Reader 指使用这个 Skill 的人。

## 1. 语义锚点

- **Audience**：日报读者，通常是知识工作者、运营者、建设者、分析师、founder、产品经理、研究者或 strategist。
- **Subject**：中文输出中使用“你”或“读者”，不要使用私人姓名。
- **Goal**：解释条目为什么影响读者的决策、理解、工作流、研究过程、风险模型或下一步行动。
- **Boundary**：只使用当前 `PROFILE.md`。如果用户尚未确认画像，以下 demo angles 仅作为占位。

## 2. Angle pool

`value_blocks[].angle` 必须是以下 key 之一：

| key | 中文名 | 使用场景 |
|---|---|---|
| `decision_impact` | 决策影响 | 影响具体选择、优先级、时机、取舍或资源分配 |
| `context_shift` | 背景变化 | 市场、政策、技术、文化、生态或 stakeholder 语境变化 |
| `cognitive_framework` | 认知框架 | 决策框架、mental model、系统视角或有用抽象 |
| `workflow_action` | 行动方法 | 工作流、清单、playbook、实验、落地步骤或运营实践 |
| `system_or_product_signal` | 系统/产品信号 | 系统行为、产品形态、UX pattern、商业模式、技术取舍或界面变化 |
| `firsthand_evidence` | 一手证据 | 一手实践、数据、案例、事故、benchmark、field note 或用户观察 |
| `risk_or_constraint` | 风险与约束 | 安全、政策、成本、信任、可靠性、合规、依赖或采用风险 |
| `counter_consensus` | 反共识视角 | 有证据支撑的非显然或反共识观点 |

## 3. 选择规则

- 只在信源证据支持时选择 1-4 个 angles。
- 不要强行填满所有 angles。
- 如果没有有用 angle，输出 `value_blocks: []`，并在 `skipped_perspectives` 说明原因。

## 4. 写作规则

- 每个 block 40-110 个中文字符。
- 每个 block 至少包含一个具体 hook：数字、公司、产品行为、工作流步骤、用户场景、取舍或风险。
- 写“为什么重要 / 如何使用 / 需要观察什么”，不要把文章再摘要一遍。
- 避免“值得关注”“影响深远”“很有启发”等空泛表达，除非后面紧跟具体理由。

## 5. 反例

- “这是一个值得关注的趋势。” 过于空泛。
- “大家都应该关注这个。” 受众和主张都太宽。
- “你可以学习一下这个工具。” 没有具体用途。
