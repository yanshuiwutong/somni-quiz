# Prompt Layout

> 文档即接口。本文件定义 `somni-graph-quiz` 的提示词分层、文件布局、上下文装配规则与降级边界。节点职责与状态字段以前置文档 [010-state-model.md](./010-state-model.md) 和 [020-node-graph.md](./020-node-graph.md) 为准。

## Goal

定义新项目中哪些节点需要 prompt、每个 prompt 的输入输出契约、共享上下文的组织方式，以及 LLM 主判定与规则兜底的边界，保证后续实现不会出现：

- 同一职责分散到多个 prompt 中互相打架
- prompt 输入上下文过少，无法识别已答题修改或多题并行命中
- 归属裁决节点越权修改 `action_mode`
- `non_content` 与 `content` 两条主分支各自复制一套提示词体系
- response 层与业务层重复判断业务逻辑
- 调试字段泄漏到用户可见响应

## Core Principles

- Prompt 只服务需要 LLM 判断的节点，不为稳定规则硬造 prompt。
- `TurnClassifyNode` 与 `ContentUnderstand` 都依赖完整短期记忆摘要，而不是只看当前 pending 题。
- `ContentUnderstand` 负责：
  - 内容单元切分
  - 单元级 `action_mode`
  - 候选题集合
  - 初步 winner
- `FinalAttribution` 只在候选集合内做纯归属，不再变更 `answer/modify/partial_completion`。
- `text_option_mapping` 只负责文本到选项的语义映射，不负责题目归属和状态流转。
- `ResponseComposerNode` 是唯一生成用户可见自然语言的节点。
- `layer1` 与 `layer2` 是分析型 prompt，不承担用户对话人设。
- `layer3` 是 Somni 对话契约层，负责把结构化真相表达成自然回复。
- `non_content` 不建立独立 prompt 家族，优先采用稳定逻辑与规则。
- 仅在无网或 LLM 不可用时走规则兜底；平时默认 LLM 优先。
- prompt 输出必须是严格结构化，不包含调试痕迹，不暴露链路推理过程。

## Prompt Directory Layout

固定目录如下：

```text
prompts/
  layer1/
    turn_classify.md
  layer2/
    content_understand.md
    final_attribution.md
    text_option_mapping.md
  layer3/
    response_composer.md
  shared/
    glossary.md
    output_contracts.md
    persona_contract.md
    language_policy.md
    response_guardrails.md
```

### Rules

- 第一层只保留 `1` 份 prompt。
- 第二层只保留 `3` 份 prompt：
  - `content_understand`
  - `final_attribution`
  - `text_option_mapping`
- `non_content` 无独立 prompt 文件。
- 第三层只保留 `1` 份 prompt：`response_composer`。
- 共享定义只放在 `shared/`，不得在各 prompt 内复制术语表。
- Somni 人设、语言策略与回复禁区统一沉淀在 `shared/`，不散落到分析节点各自定义。

## Prompt Responsibility Map

| Prompt File | Consumed By | Primary Responsibility | Must Not Do |
| --- | --- | --- | --- |
| `layer1/turn_classify.md` | `TurnClassifyNode` | 判定 `main_branch`，规范化输入，识别是否进入 `content` | 不判断具体题目归属，不落库 |
| `layer2/content_understand.md` | `ContentUnderstand` | 识别内容单元、单元动作、候选题集合、初步 winner、是否需要归属裁决 | 不直接落库，不输出最终文案 |
| `layer2/final_attribution.md` | `FinalAttribution` | 在候选题集合中选择最终归属题 | 不修改 `action_mode`，不做选项映射 |
| `layer2/text_option_mapping.md` | `ContentApply` 内 LLM 映射阶段 | 将自由文本映射成题目选项 id 集合 | 不判断题目归属，不推进状态 |
| `layer3/response_composer.md` | `ResponseComposerNode` | 以 Somni 人设根据 `turn_outcome` 和 `response_facts` 生成最终回复 | 不回写状态，不重算下一题 |

## Shared Prompt Assets

### `shared/glossary.md`

统一维护以下术语与定义：

- `main_branch`
- `non_content`
- `content`
- `action_mode`
- `answer`
- `modify`
- `partial_completion`
- `candidate_question_ids`
- `winner_question_id`
- `clarification_context`
- `pending_partial_answers`
- `answered_records`
- `skipped_question_ids`

### `shared/output_contracts.md`

统一维护所有 prompt 的输出 JSON 契约，至少覆盖：

- `TurnClassifyOutput`
- `ContentUnderstandOutput`
- `FinalAttributionOutput`
- `MappedOptionResult`
- `ResponseComposerOutput`

### `shared/persona_contract.md`

统一维护用户可见回复中的 Somni 人设基线：

- 温柔
- 治愈
- 自然
- 松弛
- 温柔的坚定感

### `shared/language_policy.md`

统一维护用户可见回复的语言切换规则：

- 默认遵循 `response_language`
- 用户换语言时允许自然切换
- 不同语言下人格保持一致

### `shared/response_guardrails.md`

统一维护用户可见回复的硬性边界：

- 不输出 markdown / JSON / debug
- 不暴露内部字段与节点名
- 不诊断
- 不制造焦虑
- 不推销
- 一次只问一个主问题

### Shared Rules

- 共享文件定义共享概念、输出格式与用户可见回复契约。
- `persona_contract.md`、`language_policy.md`、`response_guardrails.md` 只定义用户可见回复共享策略。
- 分析节点专属策略仍留在各自 prompt 中。
- 任何 prompt 调整输出字段时，必须先更新 `shared/output_contracts.md`。

## Prompt Assembly Model

每次调用 prompt 时，运行器按固定顺序装配上下文：

```text
system_role
  + shared/glossary.md
  + shared/output_contracts.md
  + node_specific_prompt.md
  + node_input_payload_json
```

### Rules

- 节点输入数据必须结构化注入，不能把完整 Python 对象字符串直接拼进 prompt。
- prompt 中使用的字段名必须与状态模型完全一致。
- 所有 few-shot 示例如果存在，也应放在对应 prompt 文件中，不要散落到代码里。
- 禁止将 debug trace、栈信息、内部异常原文直接注入给 LLM。

### Response Prompt Assembly

`response_composer` 额外加载：

```text
shared/persona_contract.md
shared/language_policy.md
shared/response_guardrails.md
```

分析节点默认不加载这些用户对话契约。

## Input Context Policy

## Layer 1 Input: `turn_classify`

`TurnClassifyNode` 的 prompt 输入必须包含：

```python
TurnClassifyPromptInput = {
    "raw_input": str,
    "normalized_input_hint": str | None,
    "session": {
        "channel": str,
        "quiz_mode": str,
        "language_preference": str,
    },
    "llm_memory_view": {
        "current_question": dict | None,
        "question_summaries": list[dict],
        "answered_summary": list[dict],
        "partial_summary": list[dict],
        "recent_turn_summaries": list[dict],
        "clarification_context": dict | None,
    },
}
```

### Why Full Short-Term Memory Is Required

因为第一层虽然不做题目归属，但它必须知道：

- 当前轮输入是否明显是控制语句
- 当前是否处于 partial follow-up
- 用户是否在补上一轮澄清
- 是否存在已答题修改线索
- 当前输入是否应进入 `content` 主分支而不是被误判为 `pullback`

若只给当前 pending 题，无法稳定支持：

- 已答题再次命中自动识别为修改
- “改上一题”类控制切换
- 同轮 `content` 域多题并行命中
- partial 补一句

## Layer 2 Input: `content_understand`

`ContentUnderstand` 的 prompt 输入必须包含：

```python
ContentUnderstandPromptInput = {
    "raw_input": str,
    "session": {
        "language_preference": str,
    },
    "llm_memory_view": {
        "current_question": dict | None,
        "question_summaries": list[dict],
        "answered_summary": list[dict],
        "partial_summary": list[dict],
        "recent_turn_summaries": list[dict],
        "clarification_context": dict | None,
    },
    "question_catalog_summary": list[dict],
}
```

### Content Understanding Rules

- 先按语义切成 `1..n` 个 `ContentUnit`。
- 每个 `ContentUnit` 独立判断 `action_mode`。
- 每个 `ContentUnit` 可有多个候选题。
- 若一个单元能稳定唯一匹配，直接给 `winner_question_id`。
- 若多个候选都合理，则：
  - `needs_attribution = true`
  - `winner_question_id = null`
- 若语义不足以支撑任何候选，返回澄清信号而不是硬猜。
- 一个单元不能被多个问题同时最终消费。

### Fragment / Unit Policy

这里不强制按词法碎片切分，而是按“可独立落到一题或一次修改意图的最小语义单元”切分。

示例：

- `我22岁，每天11点睡觉，7点起床`
  - 单元 1: `我22岁`
  - 单元 2: `每天11点睡觉，7点起床`
- `刚才年龄不是28，是29`
  - 单元 1: `刚才年龄不是28，是29`

### Why `content_understand` Is LLM-First

`content` 域内需要同时完成：

- 候选提取
- 已答题再命中转 `modify`
- partial 识别
- 普通作息与自由放松作息的语义区分
- 多单元混合输入拆解

这些都依赖上下文与语义，不适合由规则先行硬分流。规则只在无网时兜底。

## Layer 2 Input: `final_attribution`

`FinalAttribution` 的输入只包含单个待裁决单元：

```python
FinalAttributionPromptInput = {
    "unit_text": str,
    "action_mode": "answer" | "modify" | "partial_completion",
    "candidate_questions": list[dict],
    "llm_memory_view": dict,
}
```

### Final Attribution Rules

- 只允许在 `candidate_questions` 内选择 winner。
- 不得新增候选题。
- 不得把 `answer` 改成 `modify`，也不得反向修改。
- 仅输出：
  - `winner_question_id`
  - `reason`
  - `needs_clarification`
- 无更多信息时：
  - 普通作息题优先于自由放松作息题
- `23点` 这类纯时间点如果在候选集中无法唯一稳定归属，则要求澄清。
- `23点睡` 这类带动作线索的片段，应优先判为“睡眠时间相关题”，不应同时落到睡和起两题。
- 当前题只具备软优先，不能压过更强的显式语义线索。

## Layer 2 Input: `text_option_mapping`

仅在 `ContentApply` 的前两级映射失败后调用。

```python
TextOptionMappingPromptInput = {
    "question": dict,
    "raw_text": str,
    "options": list[dict],
    "matching_hints": list[str],
}
```

### Text Option Mapping Rules

- 仅在已知 `question_id` 的前提下运行。
- 只做“文本 -> 选项 id”映射。
- 允许输出：
  - `selected_options`
  - `confidence`
  - `reason`
- 不得输出新的 `question_id`。
- 对明显口语表达如 `十来分钟`、`七左右` 应支持语义映射。
- 若信心不足，返回空结果，由上层转澄清或 reject。

## Layer 3 Input: `response_composer`

`ResponseComposerNode` 的输入必须只来自 `FinalizedTurnContext`，不得自行回看节点内部临时产物。

```python
ResponseComposerPromptInput = {
    "response_language": str,
    "turn_outcome": str,
    "response_facts": dict,
    "next_question": dict | None,
    "finalized": bool,
}
```

### Response Rules

- 只基于流程结论生成用户文案。
- 必须适配 `response_language`。
- 必须遵循共享的 Somni 人设、语言策略与回复禁区契约。
- 必须能处理：
  - 记录成功
  - 修改成功
  - partial 已记录并继续追问
  - 澄清请求
  - 跳过
  - 撤回
  - 查看记录
  - 完成态总结
- 不得暴露内部字段名、节点名、fallback 细节、调试痕迹。
- 遇到 `pullback` 时，必须执行“极简共情 + 一秒拉回”。

## Output Contracts

所有 prompt 输出都必须是严格 JSON，可被解析，不允许混入自然语言解释前后缀。

### `TurnClassifyOutput`

```python
TurnClassifyOutput = {
    "main_branch": "non_content" | "content",
    "normalized_input": str,
    "reason": str,
}
```

### `ContentUnderstandOutput`

```python
ContentUnderstandOutput = {
    "content_units": list[{
        "unit_id": str,
        "unit_text": str,
        "action_mode": "answer" | "modify" | "partial_completion",
        "candidate_question_ids": list[str],
        "winner_question_id": str | None,
        "needs_attribution": bool,
        "raw_extracted_value": str | dict,
        "confidence": float,
    }],
    "clarification_needed": bool,
    "clarification_reason": str | None,
}
```

### `FinalAttributionOutput`

```python
FinalAttributionOutput = {
    "winner_question_id": str | None,
    "needs_clarification": bool,
    "reason": str,
}
```

### `MappedOptionResult`

```python
MappedOptionResult = {
    "selected_options": list[str],
    "confidence": float,
    "reason": str,
}
```

### `ResponseComposerOutput`

```python
ResponseComposerOutput = {
    "assistant_message": str,
}
```

## Fallback Strategy

## When Fallback Is Allowed

仅在以下条件之一成立时允许规则兜底：

- 无网
- LLM provider 不可用
- LLM 调用超时或返回不可解析结果

### Rules

- 不存在 `full_llm / hybrid / rule_only` 三档常态模式。
- 正常能力下默认 LLM 优先。
- fallback 是故障降级，不是常规分流。

## Fallback Scope by Node

### `TurnClassifyNode`

允许用规则兜底识别：

- 明确控制词
- 明显闲聊
- 明显空输入

### `ContentUnderstand`

允许用规则兜底识别：

- 数字题
- 明确年龄
- 强结构化时间表达
- 明确单选别名命中

### `FinalAttribution`

允许用最小规则兜底：

- 如果只剩一个候选，直接选中
- 若候选冲突且没有强线索：
  - 普通作息优先于自由放松作息
  - 仍不稳定则转澄清

### `text_option_mapping`

允许用题目 option aliases 做兜底。

### `response_composer`

允许用模板兜底，至少保证：

- 不崩溃
- 不空响应
- 语言符合 `response_language`

## Prompt Writing Conventions

- 所有 prompt 文件使用 Markdown。
- 建议统一包含以下段落：
  - `Role`
  - `Goal`
  - `Inputs`
  - `Rules`
  - `Output Contract`
  - `Examples`
- 示例优先使用本项目问卷语境，不写抽象 AI 助手例子。
- 不要求 prompt 中出现长篇“思维链”要求。
- 明确要求模型只输出结果，不输出分析过程。

## Example File Expectations

### `layer1/turn_classify.md`

应重点强调：

- 主分支互斥
- `non_content` 与 `content` 边界
- 当前轮需要完整短期记忆摘要辅助判断
- 不承担用户对话人设表达

### `layer2/content_understand.md`

应重点强调：

- LLM-first 的单元切分与候选提取
- 已答题再命中转 `modify`
- partial 识别
- 同轮多单元并行命中
- 不承担用户对话人设表达

### `layer2/final_attribution.md`

应重点强调：

- 只在候选集合中做 winner 裁决
- 普通作息优先规则
- 语义不足时澄清而不是硬选

### `layer2/text_option_mapping.md`

应重点强调：

- 只映射选项，不做归属
- 口语表达归一化

### `layer3/response_composer.md`

应重点强调：

- 唯一响应节点
- Somni 人设
- 语言切换
- 极简共情 + 一秒拉回
- 承上启下
- 不暴露调试信息

## Acceptance Scenarios

本提示词布局必须直接支撑以下场景：

1. `TurnClassifyNode` 看到完整短期记忆，能把“上一题不是28，是29”引到 `content` 主分支。
2. `ContentUnderstand` 能把 `我22岁，每天11点睡觉，7点起床` 拆成年龄题与常规作息题两个单元。
3. 已答题再次被命中时，`ContentUnderstand` 输出 `modify`，不要求显式“修改”字样。
4. `23点` 命中多个时间题候选时，`FinalAttribution` 在候选集合内裁决或要求澄清。
5. `23点睡` 不会同时归到自由入睡和自由起床两题。
6. `十来分钟` 这类表达可由 `text_option_mapping` 映射到正确选项。
7. `response_composer` 能根据 `language_preference` 切换回复语言。
8. `response_composer` 在 `pullback` 场景下具备 Somni 风格拉回能力。
9. LLM 不可用时，关键路径能由规则兜底而不改 gRPC 接口形状。

## Non-Goals

- 不为 `non_content` 单独建立一套 prompt 家族。
- 不把 `ContentUnderstand` 再拆成过多独立 LLM 节点。
- 不在 `FinalAttribution` 中重新定义动作意图。
- 不在响应层重新判断业务状态。
