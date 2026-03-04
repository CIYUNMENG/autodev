# 待办：需求与规划的质量反思（Output Critique）

当前反思模块只在**代码生成**阶段生效，且为「失败反思」：异常发生 → 批评者分析 → 重试。

**需求分析**和**规划**阶段暂无反思，需要后续补充「质量反思」机制。

---

## 背景

| 阶段 | 当前情况 | 问题 |
|------|----------|------|
| 需求分析 | 输出 RequirementOutput，很少抛异常 | `is_sufficient` 可能误判，`missing_info` 不完整，assumptions 不合理 |
| 规划 | 输出 PlanningOutput，很少抛异常 | 依赖关系错误、接口契约不一致、文件职责重叠 |
| 代码生成 | 失败时触发 reflect_on_error 并重试 | 已有 |

---

## 待实现：质量反思（Output Critique）

### 1. 需求分析质量反思

- **触发时机**：`RequirementPlanningToolAgent.analyze_and_plan()` 得到 `RequirementOutput` 之后
- **批评者职责**：评估 `is_sufficient` 是否合理、`missing_info` 是否充分、assumptions 是否合理
- **重试条件**：批评者判定「质量不达标」时，根据建议重新构造 prompt 并重跑需求分析
- **输出**：`(revised_requirement, should_retry, critique)` 或类似

### 2. 规划质量反思

- **触发时机**：`RequirementPlanningToolAgent` 得到 `PlanningOutput` 之后
- **批评者职责**：检查依赖是否有环、接口契约是否自洽、文件职责是否清晰
- **重试条件**：批评者判定「规划有问题」时，根据建议重跑规划
- **输出**：`(revised_planning, should_retry, critique)` 或类似

### 3. 实现要点

- 批评者 prompt 需单独设计，与 `reflect_on_error` 不同
- 需要「是否重试」的判定逻辑（可来自 LLM 结构化输出或规则）
- 重试次数上限，避免无限循环
- 可与现有 `reflection.py` 扩展，或新增 `reflect_on_output()` 等

---

## 参考

- 反思模式：生产者-批评者模型，批评者以独立视角评估输出质量
- 现有代码：`app/agents/reflection.py`、`app/agents/main_agent.py`、`app/agents/tool_agent.py`
