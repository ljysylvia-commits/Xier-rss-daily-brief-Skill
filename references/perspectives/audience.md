# 目标受众视角（Audience Perspective）

> 用途：定义可选 Audience value angle pool。Audience 指读者服务的目标受众。内容支柱是高级可选扩展，默认不启用。

## 1. 语义锚点

- **Audience**：读者想服务的目标受众，例如 founders、operators、product teams、strategists、researchers、clients 或 internal stakeholders。
- **Subject**：按 `PROFILE.md` 中的目标受众称呼，不要写死私人行业或私人 persona。
- **Goal**：把信源材料转译成目标受众能理解、能使用的影响。
- **Optionality**：如果用户只需要个人简报，跳过 Audience VM，只渲染 Reader blocks。

## 2. Angle pool

`value_blocks[].angle` 必须是以下 key 之一：

| key | 中文名 | 使用场景 |
|---|---|---|
| `practical_application` | 应用启发 | 可迁移的行动顺序、实现模式、评估逻辑或可避免失败 |
| `cognitive_update` | 认知更新 | 意外事实、判断修正、风险信号或被忽视的副作用 |
| `role_or_workflow_change` | 角色/流程变化 | 角色设计、团队结构、工作流变化、协作模式或运营模型 |
| `efficiency_or_quality` | 效率/质量 | 速度、质量、吞吐、覆盖、服务水平、生产率或可靠性 |
| `cost_or_resource` | 成本/资源 | 预算、成本结构、ROI、定价、资源分配、产能或采购取舍 |
| `structural_impact` | 结构性影响 | 市场结构、价值链、供需变化、分发、竞争、政策或生态 |
| `strategic_choice` | 战略选择 | 时机、优先级、长期押注、依赖、定位或高层综合判断 |

## 3. 选择规则

- 只在证据支持时选择 1-3 个 angles。
- 当条目包含具体落地细节时，优先使用 `practical_application`。
- 不要只把 Reader block 的主语换掉后重复输出；如果观点重叠，应跳过。

## 4. 写作规则

- 每个 block 40-110 个中文字符。
- 至少包含一个具体 hook：数字、公司、产品行为、工作流步骤、用户场景、成本 / ROI 细节或风险。
- 把专业内容翻译成符合目标受众真实需求的语言。
- 除非信源本身指向某个行业，不要假设特定私人行业。

## 5. Content pillars 可选扩展

默认不输出 content pillars。

只有当 `features.pillar_mapping = true` 且 orchestrator 明确把 `references/pillar_config.json` 放入 prompt 时，Audience VM 才可以输出 0-2 个 `pillars` key。

- 只有当条目可复用为写作、brief、研究或讨论材料时，才分配 pillar。
- 不要给浅层发布噪声或低相关市场更新分配 pillar。
- 如果分配 pillar，至少一个 Audience value block 要写出具体可复用角度。

## 6. 反例

- “某个私人行业的老板应该关注这个。” 泄漏私人 persona，且过于空泛。
- “这对目标受众很有帮助。” 没有具体机制。
- “这条适合作为内容素材。” 只说用途，没有说明有用角度。
