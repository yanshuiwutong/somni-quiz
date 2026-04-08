# State Model

> 文档即接口。本文件定义 `somni-graph-quiz` 的状态契约基线。后续节点实现、适配层映射、prompt 上下文、测试样例都以本文件为准。

## Goal

定义新项目的核心状态对象与跨节点接口，保证以下能力可以在统一状态模型上成立：

- 意图层只做识别与候选输出，不直接落库
- 已答题再次命中自动视为修改，不要求显式“修改”字样
- 多题冲突先输出候选集合，再由后续归属节点裁决
- partial 立即落状态，后续只补缺口
- partial 两次仍无效可跳过，但保留部分已答信息
- 显式跳题与自动跳题并存
- 对外仅有一个最终响应节点生成用户文案
- 响应语言可由外部输入指定，并供响应层切换语言
- 仅支持 `content` 域内混合意图多题命中，不支持 `non_content + content` 跨主分支并行执行

## Core Principles

- `question_catalog` 是静态题库定义，只读。
- `session_memory` 是运行态会话记忆，承载业务真相。
- `turn` 与 `artifacts` 是本轮过程态，不得被当作长期业务真相来源。
- 节点不得直接原地修改状态，只能输出 `state_patch` 交由 runtime 合并。
- 第二层分支只输出结构化结果，不直接输出最终用户文案。
- 主分支保持互斥：`non_content | content`。
- `content` 单元在进入 `ContentApply` 前，允许已经携带标准化答案字段。

## GraphState Top Level

`GraphState` 顶层固定为六块：

```python
GraphState = {
    "session": SessionContext,
    "question_catalog": QuestionCatalog,
    "session_memory": SessionMemory,
    "runtime": RuntimeState,
    "turn": TurnContext,
    "artifacts": ArtifactsState,
}
```

### Read/Write Boundary

- 永远只读：
  - `session`
  - `question_catalog`
- 允许通过 patch 更新：
  - `session_memory`
  - `runtime`
  - `turn`
  - `artifacts`

## SessionContext

`session` 表示外部会话上下文，只读。

```python
SessionContext = {
    "session_id": str,
    "channel": "grpc" | "streamlit",
    "quiz_mode": str,
    "language_preference": str,
    "language_source": "grpc_input" | "streamlit_input" | "default",
    "started_at": str,
}
```

### Rules

- `language_preference` 优先来自 gRPC 输入。
- `language_source` 仅说明来源，不参与业务判断。
- 节点执行过程中默认不回写 `session.language_preference`。

## QuestionCatalog

`question_catalog` 表示静态题库定义，只读。

```python
QuestionCatalog = {
    "question_order": list[str],
    "question_index": dict[str, QuestionDefinition],
}

QuestionDefinition = {
    "question_id": str,
    "title": str,
    "description": str,
    "input_type": str,
    "options": list[OptionDefinition],
    "tags": list[str],
    "metadata": QuestionMetadata,
}

OptionDefinition = {
    "option_id": str,
    "label": str,
    "aliases": list[str],
}

QuestionMetadata = {
    "allow_partial": bool,
    "structured_kind": str | None,
    "response_style": str | None,
    "matching_hints": list[str],
}
```

### Rules

- 题型差异优先体现在 `QuestionDefinition` 和 `metadata` 中。
- 节点不得在运行期修改题目定义。
- 新题型、新匹配提示、新响应风格优先新增 `metadata`，而不是散落到节点内部 `if/else`。

## SessionMemory

`session_memory` 是运行态业务真相。

```python
SessionMemory = {
    "current_question_id": str | None,
    "pending_question_ids": list[str],
    "question_states": dict[str, QuestionRuntimeState],
    "answered_records": dict[str, AnswerRecordEntry],
    "pending_partial_answers": dict[str, PartialAnswerEntry],
    "pending_modify_context": ModifyContext | None,
    "skipped_question_ids": list[str],
    "previous_answer_record": dict[str, AnswerRecordEntry] | None,
    "recent_turns": list[RecentTurnEntry],
    "unanswered_question_ids": list[str],
    "answered_question_ids": list[str],
    "partial_question_ids": list[str],
    "clarification_context": ClarificationContext | None,
}
```

### QuestionRuntimeState

```python
QuestionRuntimeState = {
    "status": "unanswered" | "answered" | "partial" | "skipped",
    "attempt_count": int,
    "last_action_mode": "answer" | "modify" | "partial_completion" | None,
}
```

### AnswerRecordEntry

```python
AnswerRecordEntry = {
    "question_id": str,
    "selected_options": list[str],
    "input_value": str,
    "field_updates": dict[str, str],
}
```

### PartialAnswerEntry

```python
PartialAnswerEntry = {
    "question_id": str,
    "filled_fields": dict[str, str],
    "missing_fields": list[str],
    "source_question_state": "partial" | "skipped_partial",
}
```

### ModifyContext

```python
ModifyContext = {
    "target_question_ids": list[str],
    "raw_user_input": str,
    "needs_confirmation": bool,
}
```

### ClarificationContext

```python
ClarificationContext = {
    "reason": str,
    "candidate_question_ids": list[str],
    "action_mode": "answer" | "modify" | "partial_completion" | None,
    "raw_fragment": str,
}
```

### Rules

- `answered_records` 只承载已落库答案。
- `pending_partial_answers` 单独承载 partial，不混入完整答案记录。
- 某题若已进入 `skipped`，但仍存在 `pending_partial_answers[question_id]`，则它语义上属于“可恢复的 skipped partial”。
- `clarification_context` 负责承接“上一轮不够明确、下一轮补一句”的场景。
- `previous_answer_record` 用于撤回，不用于正常导航。
- 下列 `session_memory` 字典字段在 patch 合并时按整表替换，而不是递归保留旧 key：
  - `answered_records`
  - `pending_partial_answers`
  - `question_states`
  - `previous_answer_record`

## RuntimeState

`runtime` 只存运行器自身状态，不存业务答案。

```python
RuntimeState = {
    "llm_available": bool,
    "finalized": bool,
    "current_turn_index": int,
    "fallback_used": bool,
}
```

### Rules

- 仅在无网或 LLM 不可用时允许 `fallback_used=True`。
- 不支持 `full_llm / hybrid / rule_only` 三档模式。

## TurnContext

`turn` 是本轮临时上下文。

```python
TurnContext = {
    "raw_input": str,
    "input_mode": "message" | "direct_answer",
    "normalized_input": str,
    "main_branch": "non_content" | "content" | None,
    "non_content_intent": str,
    "response_language": str,
    "content_units": list[ContentUnit],
    "branch_results": dict[str, dict],
}
```

### ContentUnit

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

### Rules

- `response_language` 默认继承 `session.language_preference`。
- 本轮允许覆盖 `response_language`，但不回写 `session_memory`。
- `main_branch` 只允许：
  - `non_content`
  - `content`
- `non_content_intent` 记录第一层分类后的控制或 pullback 子意图，默认值为 `none`。
- 不支持同轮 `non_content + content` 跨主分支并行执行。
- `selected_options / input_value / field_updates / missing_fields` 允许由理解层直接产出，供 `ContentApply` 优先消费。

## ArtifactsState

`artifacts` 保存结构化过程产物。

```python
ArtifactsState = {
    "trace_entries": list[TraceEntry],
    "mapping_artifacts": list[dict],
    "response_facts": dict[str, str | list | dict],
    "llm_inputs_summary": list[dict],
    "llm_outputs_summary": list[dict],
}
```

### Rules

- `artifacts` 用于测试、排障、回放。
- `artifacts` 不得作为长期业务真相来源。

## Memory Views

由 `question_catalog + session_memory` 派生两个视图：

```python
RuntimeMemoryView = {
    "current_question_id": str | None,
    "pending_question_ids": list[str],
    "question_states": dict[str, QuestionRuntimeState],
    "answered_question_ids": list[str],
    "partial_question_ids": list[str],
    "skipped_question_ids": list[str],
    "clarification_context": ClarificationContext | None,
}

LLMMemoryView = {
    "current_question": dict | None,
    "question_summaries": list[dict],
    "answered_summary": list[dict],
    "partial_summary": list[dict],
    "recent_turn_summaries": list[dict],
    "clarification_context": ClarificationContext | None,
}
```

### Rules

- `runtime_memory_view` 服务 runtime 和状态流转。
- `llm_memory_view` 只暴露必要摘要，不暴露杂散 debug 字段。

## External/Input Contracts

### TurnInput

```python
TurnInput = {
    "session_id": str,
    "channel": "grpc" | "streamlit",
    "input_mode": "message" | "direct_answer",
    "raw_input": str,
    "direct_answer_payload": dict | None,
    "language_preference": str | None,
}
```

### NodeInput

```python
NodeInput = {
    "graph_state": GraphState,
    "context": dict,
}
```

### NodeOutput

```python
NodeOutput = {
    "state_patch": dict,
    "branch_decision": dict | None,
    "artifacts": dict,
    "terminal_signal": str | None,
    "fallback_used": bool,
}
```

### TurnResult

```python
TurnResult = {
    "updated_graph_state": GraphState,
    "answer_record": dict,
    "pending_question": dict | None,
    "assistant_message": str,
    "finalized": bool,
    "final_result": dict | None,
}
```

## Action Modes

`content` 域内部显式使用三种动作：

- `answer`
- `modify`
- `partial_completion`

### Rules

- `answer`
  - 目标题此前未完成
- `modify`
  - 目标题此前已完整作答，本轮命中视为修改
- `partial_completion`
  - 目标题此前为 partial，本轮是在补齐缺失部分

对外接口不新增第三种公开动作类型；`partial_completion` 只作为 graph 内核内部动作存在。

## State Transition Rules

### Question State Transitions

- 未答题被完整命中：
  - `unanswered -> answered`
- 多字段题只命中部分：
  - `unanswered -> partial`
- partial 补全成功：
  - `partial -> answered`
- 已答题再次命中：
  - 保持 `answered`，并触发 `modify`
- 显式跳题：
  - 进入 `skipped`
- 某题两次无效响应：
  - 进入 `skipped`
- partial 两次仍未补全：
  - 进入 `skipped`
  - 保留 `pending_partial_answers`

### Re-entry Rules

- `skipped` 题再次被命中时：
  - 可重新进入 `answer`
  - 或重新进入 `partial_completion`
- `skipped` 且仍保留 partial 的题再次被命中时：
  - 若本轮输入正好补其缺失字段，则优先恢复为 `partial_completion`
  - 不要求用户先显式说“回到上一题”
- `clarification_context` 存在时：
  - 下一轮优先将补充输入与该上下文对齐

### Skipped Partial Resume Rules

- 对 `time_range` 这类支持 partial 的题：
  - `11点睡 -> 跳过 -> 9点起`
  - 应恢复并合并为同一题的完整答案，而不是重新开始一题新答案
- 只有当新输入命中该题缺失字段时，才自动恢复 skipped partial
- 若新输入与缺失字段无关，则继续按当前 pending 题正常处理

## Intent and Attribution Rules

- 意图层只输出：
  - 主分支
  - 内容单元的 `action_mode`
  - 候选题集合
- 意图层不做最终落库，但允许在题目已闭环时直接输出标准化答案字段。
- 若一个内容单元命中多题：
  - 先评估哪些候选题能形成合法答案闭环
  - 只有多个候选都成立时才保留候选集合并进入归属裁决
- 无额外信息时：
  - 普通作息题优先于自由放松作息题

## Mixed Hit Rules

### Supported

仅支持 `content` 域内混合命中：

- `answer + modify`
- `answer + partial_completion`
- `modify + partial_completion`
- `answer + modify + partial_completion`

### Not Supported

不支持跨主分支并行执行：

- `non_content + content`

例如“跳过这题，我平时11点睡7点起”这类输入，当前架构只能正式执行一个主分支。

## Response Rules

- 第二层分支只输出结构化结果与参考事实。
- 第三层唯一响应节点根据：
  - `FinalizedTurnContext`
  - `response_language`
  - 分支结果
  生成最终 `assistant_message`。

## Examples

### Example 1: GraphState Snapshot

```json
{
  "session": {
    "session_id": "quiz-001",
    "channel": "grpc",
    "quiz_mode": "dynamic",
    "language_preference": "zh-CN",
    "language_source": "grpc_input",
    "started_at": "2026-04-05T10:00:00+08:00"
  },
  "question_catalog": {
    "question_order": ["question-01", "question-02", "question-03"],
    "question_index": {
      "question-02": {
        "question_id": "question-02",
        "title": "你平时几点睡、几点起？",
        "description": "",
        "input_type": "time_range",
        "options": [],
        "tags": ["作息"],
        "metadata": {
          "allow_partial": true,
          "structured_kind": "time_range",
          "response_style": "followup",
          "matching_hints": ["平时", "通常", "作息"]
        }
      }
    }
  },
  "session_memory": {
    "current_question_id": "question-02",
    "pending_question_ids": ["question-02", "question-03"],
    "question_states": {
      "question-02": {
        "status": "partial",
        "attempt_count": 1,
        "last_action_mode": "answer"
      }
    },
    "answered_records": {},
    "pending_partial_answers": {
      "question-02": {
        "question_id": "question-02",
        "filled_fields": {"bedtime": "23:00"},
        "missing_fields": ["wake_time"],
        "source_question_state": "partial"
      }
    },
    "pending_modify_context": null,
    "skipped_question_ids": [],
    "previous_answer_record": null,
    "recent_turns": [],
    "unanswered_question_ids": ["question-02", "question-03"],
    "answered_question_ids": [],
    "partial_question_ids": ["question-02"],
    "clarification_context": null
  },
  "runtime": {
    "llm_available": true,
    "finalized": false,
    "current_turn_index": 2,
    "fallback_used": false
  },
  "turn": {
    "raw_input": "7点起",
    "input_mode": "message",
    "normalized_input": "7点起",
    "main_branch": "content",
    "non_content_intent": "none",
    "response_language": "zh-CN",
    "content_units": [],
    "branch_results": {}
  },
  "artifacts": {
    "trace_entries": [],
    "mapping_artifacts": [],
    "response_facts": {},
    "llm_inputs_summary": [],
    "llm_outputs_summary": []
  }
}
```

### Example 2: TurnInput

```json
{
  "session_id": "quiz-001",
  "channel": "grpc",
  "input_mode": "message",
  "raw_input": "我平时11点睡7点起，刚才年龄不是28，是29",
  "direct_answer_payload": null,
  "language_preference": "zh-CN"
}
```

### Example 3: NodeOutput

```json
{
  "state_patch": {
    "turn": {
      "main_branch": "content",
      "content_units": [
        {
          "unit_id": "unit-1",
          "unit_text": "我平时11点睡7点起",
          "action_mode": "answer",
          "candidate_question_ids": ["question-02"],
          "winner_question_id": "question-02",
          "needs_attribution": false,
          "raw_extracted_value": "23:00-07:00",
          "selected_options": [],
          "input_value": "",
          "field_updates": {
            "bedtime": "23:00",
            "wake_time": "07:00"
          },
          "missing_fields": []
        },
        {
          "unit_id": "unit-2",
          "unit_text": "刚才年龄不是28，是29",
          "action_mode": "modify",
          "candidate_question_ids": ["question-01"],
          "winner_question_id": "question-01",
          "needs_attribution": false,
          "raw_extracted_value": "29",
          "selected_options": ["B"],
          "input_value": "",
          "field_updates": {},
          "missing_fields": []
        }
      ]
    }
  },
  "branch_decision": {
    "main_branch": "content"
  },
  "artifacts": {},
  "terminal_signal": null,
  "fallback_used": false
}
```

### Example 4: TurnResult

```json
{
  "updated_graph_state": {},
  "answer_record": {
    "answers": [
      {"question_id": "question-01", "input_value": "29"},
      {"question_id": "question-02", "input_value": "23:00-07:00"}
    ]
  },
  "pending_question": {
    "question_id": "question-03"
  },
  "assistant_message": "已记录你的年龄修改和平时作息，接下来请回答下一题。",
  "finalized": false,
  "final_result": null
}
```

## Acceptance Scenarios

本状态模型必须能承载以下场景：

1. 当前题正常回答
2. 已答题再次命中并自动转 `modify`
3. 普通作息与自由放松作息的候选集合输出
4. 单片段作息进入 `partial`
5. partial 后补全
6. partial 两次无效后跳过但保留部分答案
7. partial 跳过后，后续补输入可自动恢复并补全
8. 显式“下一题/跳过”
9. “改上一题”类控制修改指令
10. gRPC 输入语言标识影响响应语言
11. 同轮 `content` 域内同时命中一题 `answer` 和另一题 `modify`
12. 含控制词和答题内容的混合输入，只执行一个主分支
