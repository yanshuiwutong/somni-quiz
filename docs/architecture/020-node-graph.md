# Node Graph

> 文档即接口。本文件定义 `somni-graph-quiz` 的节点图、执行顺序与节点职责边界。状态对象与字段语义以前置文档 [010-state-model.md](./010-state-model.md) 为准。

## Goal

定义新项目单轮执行链、三层节点图、第二层分支内部顺序，以及 `ContentApply`、`TurnFinalizeNode`、`ResponseComposerNode` 的职责边界，保证后续实现不会回流成“大型 service 文件”。

本文件必须直接支撑以下能力：

- 主分支互斥：`non_content | content`
- `content` 域内支持 `answer + modify + partial_completion` 混合多题命中
- 意图层做识别、动作判断、候选裁剪，并可在题目已闭环时直接输出标准化答案字段，但仍不直接落库
- 多题冲突先输出候选集合，再由归属节点裁决
- partial 立即落状态、只补缺失字段、两次无效后跳过但保留 partial
- 显式跳题与自动跳题并存
- `skipped` 不算完成，只有所有题都 answered 才能 completed
- 任一轮只允许一个响应节点输出最终用户文案

## Core Principles

- 任何一轮都必须经过：
  - 一个入口分类节点
  - 一个第二层业务分支
  - 一个流程收口节点
  - 一个唯一响应节点
- 第二层可以结束业务处理，但不能绕过第三层。
- `TurnFinalizeNode` 是唯一流程判断中心。
- `ResponseComposerNode` 是唯一用户文案生成中心。
- 第二层分支只输出结构化结果，不直接输出最终文案。

## Single-Turn Execution Chain

单轮执行链固定为：

```text
TurnClassifyNode
  -> NonContentBranch | ContentBranch
  -> TurnFinalizeNode
  -> ResponseComposerNode
```

### Rules

- 任一轮都必须进入 `TurnFinalizeNode`。
- 任一轮都必须由 `ResponseComposerNode` 生成最终 `assistant_message`。
- 不支持同轮 `non_content + content` 跨主分支并行执行。

## Layer 1

### TurnClassifyNode

#### Input

- `TurnInput`
- `runtime_memory_view`
- 必要的 `llm_memory_view` 摘要

#### Output

- `turn.main_branch = non_content | content`
- `turn.non_content_intent = none | identity | pullback_chat | ...`
- `turn.normalized_input`

#### Responsibilities

- 判定主分支
- 判定 `non_content` 子意图
- 规范化本轮输入
- 为第二层准备最小上下文

#### Must Not

- 不落库
- 不输出最终文案
- 不直接解释题目答案

#### Terminal Behavior

- 不能终止本轮

## Layer 2 Overview

第二层只允许进入一个主分支：

- `NonContentBranch`
- `ContentBranch`

两条分支都必须输出统一的 `branch_result` 形状，至少包含：

```python
BranchResult = {
    "branch_type": "non_content" | "content",
    "state_patch": dict,
    "applied_question_ids": list[str],
    "modified_question_ids": list[str],
    "partial_question_ids": list[str],
    "skipped_question_ids": list[str],
    "rejected_unit_ids": list[str],
    "clarification_needed": bool,
    "response_facts": dict,
}
```

### Rules

- 第三层只消费统一 `branch_result`，不回头读取第二层内部临时对象。
- 第二层内部可以复杂，但对第三层暴露的结果必须统一。

## Layer 2A: NonContentBranch

`NonContentBranch` 保持轻量，内部固定为两个阶段；两个阶段可写在同一模块中，不要求提升为独立 graph 节点。

```text
NonContentDetect
  -> NonContentApply
```

### NonContentDetect

#### Input

- `turn.raw_input`
- `runtime_memory_view`

#### Output

```python
NonContentDetection = {
    "non_content_mode": "control" | "pullback",
    "control_action": str | None,
    "pullback_reason": str | None,
}
```

#### Coverage

- `control`
  - 下一题
  - 跳过
  - 撤回
  - 查看全部
  - 查看上下题记录
  - 改上一题
- `pullback`
  - 无效语句
  - 闲聊
  - 跑题

### NonContentApply

#### Input

- `NonContentDetection`
- `session_memory`

#### Output

- `BranchResult`

#### Responsibilities

- 执行控制动作
- 生成结构化流程结果
- 生成最小 `state_patch`

#### Must Not

- 不解释内容题答案
- 不输出最终用户文案

## Layer 2B: ContentBranch

`ContentBranch` 是问卷主路径，内部执行顺序固定为：

```text
ContentUnderstand
  -> FinalAttribution (only when needed)
  -> ContentApply
```

### ContentUnderstand

#### Input

- `turn.raw_input`
- `llm_memory_view`
- `question_catalog`

#### Output

一个或多个 `ContentUnit`：

```python
ContentUnit = {
    "unit_id": str,
    "unit_text": str,
    "action_mode": "answer" | "modify" | "partial_completion",
    "candidate_question_ids": list[str],
    "winner_question_id": str | None,
    "needs_attribution": bool,
    "raw_extracted_value": str | dict,
    "selected_options": list[str],
    "input_value": str,
    "field_updates": dict[str, str],
    "missing_fields": list[str],
}
```

#### Responsibilities

- 内容单元提取
- `action_mode` 判定
- 候选题集合输出
- 初步 winner 选择
- 当某题已经形成合法答案闭环时，直接输出标准化答案字段
- 澄清时给出尽量具体的目标题信息

#### Must Not

- 不直接落库
- 不输出最终文案

### FinalAttribution

#### When It Runs

- 仅当某个 `ContentUnit.needs_attribution = true`

#### Input

- 单个 `ContentUnit`
- `llm_memory_view`
- `question_catalog`

#### Output

- 更新后的 `ContentUnit`

#### Responsibilities

- 只在候选集合内做最终裁决
- 仅在多个真实可行候选仍同时成立时运行

#### Must Not

- 不改写 `action_mode`
- 不落库
- 不输出文案

### ContentApply

`ContentApply` 是单一节点，但内部固定分两个子阶段：

```text
interpret_to_patch
  -> commit_patch
```

#### Responsibilities

- 将已归属的 `ContentUnit` 转成标准 patch
- 优先消费理解层已产出的 `selected_options / input_value / field_updates / missing_fields`
- 当理解层未完成标准化时，再调用结构化 parser、规则映射、LLM 映射补齐
- 提交到 `session_memory`
- 生成统一 `BranchResult`

#### Must Not

- 不重新判断题目归属
- 不直接生成最终用户文案

## ContentApply Detailed Rules

### A. interpret_to_patch

#### Input

- 已确认归属的 `ContentUnit`
- `question_catalog`
- `session_memory`

#### Output

- `patch_candidates`
- `apply_rejections`

每个 `patch_candidate` 至少包含：

```python
PatchCandidate = {
    "question_id": str,
    "action_mode": "answer" | "modify" | "partial_completion",
    "patch_kind": str,
    "selected_options": list[str],
    "input_value": str,
    "field_updates": dict[str, str],
    "state_effect": str,
    "source_unit_id": str,
}
```

#### Patch Kind

- `option_answer`
- `text_answer`
- `structured_answer`
- `partial_answer`
- `modify_answer`

### B. Mapping Order

按题型固定执行顺序：

1. 理解层已闭环结果
2. 结构化解析
3. 规则映射
4. LLM 映射

#### Pre-Resolved Unit Consumption

- 若 `ContentUnit` 已携带合法的 `selected_options`，优先直接消费，不再重复做题内选项猜测。
- 若 `ContentUnit` 已携带 `field_updates / missing_fields`，优先按结构化答案处理。
- 只有理解层没有给出可用标准化结果时，`ContentApply` 才继续做题内映射。

#### Structured Parsing

优先用于：

- `time_range`
- 数值题
- 日期题
- 其他格式强约束题

结果：

- 完整解析 -> `structured_answer`
- 部分解析 -> `partial_answer`
- 失败 -> 进入 reject 或后续澄清

#### Rule Mapping

优先用于单选、多选、枚举型题。

规则输入：

- option label
- option aliases
- `matching_hints`
- 文本归一化结果

规则结果：

- 唯一命中 -> 直接产出标准 `selected_options`
- 多个命中 -> `ambiguous`
- 完全不命中 -> 进入 LLM 映射

#### LLM Mapping

仅在规则无法稳定唯一命中时触发。

LLM 输出必须固定为：

```python
MappedOptionResult = {
    "selected_options": list[str],
    "confidence": float,
    "reason": str,
}
```

### C. Action Mode Validation

- `answer`
  - 允许题此前为 `unanswered` 或 `skipped`
- `modify`
  - 仅允许题此前为 `answered`
- `partial_completion`
  - 仅允许题此前为 `partial`

不合法时直接 reject，原因至少包括：

- `missing_winner`
- `invalid_action_mode_for_state`
- `option_mapping_failed`
- `structured_parse_failed`
- `ambiguous_unit`

### D. commit_patch

#### Input

- `patch_candidates`
- `session_memory`

#### Output

- `state_patch`
- `BranchResult`

#### Storage Rules

- 完整答案只写入 `answered_records`
- partial 只写入 `pending_partial_answers`
- `question_states` 只表达流程态，不重复存答案内容
- `previous_answer_record` 只服务最近一次可撤回修改

#### Complete Answer

- 写入 `answered_records[question_id]`
- 更新 `question_states[question_id].status = answered`
- 从 `pending_question_ids / unanswered_question_ids / partial_question_ids` 中移除或重排

#### Modify

- 覆盖 `answered_records[question_id]`
- 保持 `status = answered`
- 写入最近一次可撤回基线

#### Partial Answer

- 不写 `answered_records`
- 写入 `pending_partial_answers[question_id]`
- 更新 `status = partial`

#### Partial Completion

- 先合并旧 partial 与新字段
- 若补齐：
  - 删除 `pending_partial_answers[question_id]`
  - 写入 `answered_records[question_id]`
  - `status = answered`
- 若仍不完整：
  - 更新 `pending_partial_answers`
  - 维持 `status = partial`

#### Partial Skip Rule

- partial 被跳过时，不删除 partial
- 只加入 `skipped_question_ids`
- 继续保留 `pending_partial_answers`
- 若后续输入能补该题缺失字段，则优先把该题恢复为 `partial_completion`
- 补全成功后，需同时移除：
  - `pending_partial_answers[question_id]`
  - `partial_question_ids` 中的该题
  - `skipped_question_ids` 中的该题

#### Same-Turn Multi-Unit Rule

- 一轮多个 unit 可部分成功
- 明确成功的正常提交
- 失败的进入 `rejected_unit_ids`
- 不因为单个 unit 失败回滚整轮

#### Same-Turn Same-Question Rule

- 同一轮多个 unit 命中同一题时，默认视为冲突
- `commit_patch` 不负责自动合并

## Layer 3

第三层固定只保留两个节点：

- `TurnFinalizeNode`
- `ResponseComposerNode`

### TurnFinalizeNode

#### Input

- `GraphState`
- 第二层统一 `BranchResult`
- `question_catalog.question_order`

#### Output

`FinalizedTurnContext` 至少包含：

```python
FinalizedTurnContext = {
    "turn_outcome": str,
    "updated_answer_record": dict,
    "updated_question_states": dict,
    "current_question_id": str | None,
    "next_question": dict | None,
    "finalized": bool,
    "response_language": str,
    "response_facts": dict,
}
```

#### Responsibilities

- 合并第二层 patch
- 推进 `session_memory`
- 选择下一题
- 判断完成态
- 统一生成 `turn_outcome`
- 生成响应层所需事实

### Next Question Priority

下一题选择优先级固定为：

1. 显式 `control` 导航结果
2. 当前题 partial follow-up
3. 普通 `pending_question_ids`
4. `skipped` 且未完成的题
5. 完成态

### Partial Follow-Up Rules

- 新 partial 产生时：
  - 默认继续追问该题缺失字段
- partial 补了一部分但仍未完整：
  - 继续追问剩余字段
- partial 两次无效：
  - 加入 `skipped_question_ids`
  - 保留 `pending_partial_answers`
  - 转到下一个普通 pending 题
- 被跳过的 partial 题再次命中：
  - 若本轮输入正好命中缺失字段，继续走 `partial_completion`
  - 若本轮输入不命中缺失字段，不抢占当前 pending 题

### Attempt Count Rules

- 当前题本轮无有效进展：
  - `attempt_count += 1`
- 当前题本轮有有效进展：
  - `attempt_count` 重置
- `attempt_count >= 2` 且无显式控制：
  - 触发自动跳过

### Completion Rules

- `skipped` 不算完成
- 只有所有题都 `answered` 时才允许：
  - `turn_outcome = completed`
  - `finalized = true`

### turn_outcome Enum

`TurnFinalizeNode` 输出单一主 outcome，至少包括：

- `answered`
- `modified`
- `partial_recorded`
- `clarification`
- `skipped`
- `undo_applied`
- `view_only`
- `pullback`
- `completed`

混合结果时按固定优先级选主 outcome，其余通过 `response_facts` 表达。

推荐优先级：

1. `completed`
2. `modified`
3. `answered`
4. `partial_recorded`
5. `skipped`
6. `clarification`
7. `undo_applied`
8. `view_only`
9. `pullback`

### Response Facts

`TurnFinalizeNode` 至少提供：

- `recorded_question_ids`
- `modified_question_ids`
- `partial_question_ids`
- `missing_fields_by_question`
- `skipped_question_ids`
- `clarification_reason`
- `clarification_question_id`
- `clarification_question_title`
- `clarification_kind`
- `next_question_id`
- `finalized`
- `response_language`

## ResponseComposerNode

### Input

- `FinalizedTurnContext`

### Output

- 唯一 `assistant_message`

### Responsibilities

- 根据 `turn_outcome`、`response_language`、`response_facts` 生成最终文案
- 统一处理：
  - 记录成功
  - 修改成功
  - 撤回成功
  - 跳题成功
  - partial 已记录并继续追问
  - 澄清请求
  - 完成态总结
- `clarification` 时只围绕 `response_facts` 指向的目标问题追问
- `completed` 时基于 `updated_answer_record` 做结束态总结

### Must Not

- 不改状态
- 不重算下一题
- 不参与业务判断

## Node Responsibility Matrix

| Node | Can mutate business state | Can end branch processing | Can output final user text |
| --- | --- | --- | --- |
| `TurnClassifyNode` | No | No | No |
| `NonContentBranch` | Yes, via patch | Yes, but must continue to layer 3 | No |
| `ContentBranch` | Yes, via patch | No | No |
| `TurnFinalizeNode` | Yes, via patch merge | No | No |
| `ResponseComposerNode` | No | Final step | Yes |

## Example Execution Paths

### Example 1: Normal Content Turn

```text
TurnClassifyNode -> ContentBranch
  ContentUnderstand
  ContentApply
-> TurnFinalizeNode
-> ResponseComposerNode
```

### Example 2: Content Turn With Attribution

```text
TurnClassifyNode -> ContentBranch
  ContentUnderstand
  FinalAttribution
  ContentApply
-> TurnFinalizeNode
-> ResponseComposerNode
```

### Example 3: Explicit Skip

```text
TurnClassifyNode -> NonContentBranch
  NonContentDetect(control=skip)
  NonContentApply
-> TurnFinalizeNode
-> ResponseComposerNode
```

### Example 4: Mixed Content Answer + Modify

```text
TurnClassifyNode -> ContentBranch
  ContentUnderstand
    unit-1 -> answer -> question-02
    unit-2 -> modify -> question-01
  ContentApply
-> TurnFinalizeNode
  turn_outcome = modified
  response_facts also include recorded_question_ids
-> ResponseComposerNode
```

## Acceptance Scenarios

本节点图设计必须直接覆盖：

1. 当前题正常 answer
2. 同轮 `content` 域内一题 `answer` + 一题 `modify`
3. 普通作息 vs 自由放松作息进入候选集合并再裁决
4. 单片段作息进入 partial，并触发 follow-up
5. partial 补全成功
6. partial 两次无效后进入 `skipped` 且保留 partial
7. partial 被显式跳过后，后续补输入可自动恢复补全
8. 显式“下一题/跳过”
9. “改上一题”
10. 含控制词和答题内容的混合输入，只执行一个主分支
11. 所有题 answered 后进入 `completed`
12. 单选题在理解层即可完成唯一题内闭环
13. 澄清只围绕已识别出的目标问题，不回退成泛化追问

## Non-Goals

- 不扩展为 `non_content + content` 跨主分支混合执行
- 不在第二层生成最终用户文案
- 不引入额外正式 graph 节点去替代 `ContentApply` 内部子阶段
