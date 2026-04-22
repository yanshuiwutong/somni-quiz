# Output Contracts

## Goal

统一所有 prompt 的结构化输出格式。模型必须只输出合法 JSON，不得输出解释前缀、代码围栏、调试信息或额外自然语言。

## General Rules

- 所有枚举值必须严格使用本文定义的字面量。
- 未要求的字段不要输出。
- 无值时使用 `null` 或空数组，不要自造占位字符串。
- 不输出内部推理过程。
- 用户可见回复类输出只能通过 `ResponseComposerOutput` 提供。

## `TurnClassifyOutput`

```json
{
  "main_branch": "non_content",
  "non_content_intent": "navigate_next",
  "normalized_input": "下一题",
  "reason": "explicit control expression"
}
```

字段说明：

- `main_branch`
  - `"non_content"` | `"content"`
- `non_content_intent`
  - 控制或 pullback 子意图；若主分支为 `content` 通常为 `"none"`
- `normalized_input`
  - 输入归一化结果
- `reason`
  - 简短原因说明，供内部记录

## `CompanionDecisionOutput`

```json
{
  "companion_action": "enter",
  "companion_mode": "smalltalk",
  "continue_chat_intent": "strong",
  "answer_status_override": "NOT_RECORDED",
  "reason": "user is shifting into free chat"
}
```

字段说明：

- `companion_action`
  - `"enter"` | `"stay"` | `"exit"` | `"none"`
- `companion_mode`
  - `"smalltalk"` | `"supportive"` | `"none"`
- `answer_status_override`
  - `"NOT_RECORDED"` | `"none"`
- `continue_chat_intent`
  - `"strong"` | `"weak"` | `"none"`
- `reason`
  - 简短内部原因说明

## `ContentUnderstandOutput`

```json
{
  "content_units": [
    {
      "unit_id": "unit-1",
      "unit_text": "我22岁",
      "action_mode": "answer",
      "candidate_question_ids": ["question-01"],
      "winner_question_id": "question-01",
      "needs_attribution": false,
      "raw_extracted_value": "22",
      "selected_options": ["A"],
      "input_value": "",
      "field_updates": {},
      "missing_fields": [],
      "confidence": 0.98
    }
  ],
  "clarification_needed": false,
  "clarification_reason": null,
  "clarification_question_id": null,
  "clarification_question_title": null,
  "clarification_kind": null
}
```

字段说明：

- `content_units`
  - 内容单元数组，可为空
  - 单元可直接携带标准化答案字段
  - 单选题若已闭环，`selected_options` 必须是唯一选项 id
  - 结构化题可通过 `field_updates / missing_fields` 表示完整或部分闭环结果
- `clarification_needed`
  - 当整条输入无法稳定继续时为 `true`
- `clarification_reason`
  - 澄清原因，若无需澄清则为 `null`
- `clarification_question_id`
  - 若已识别出需要澄清的目标问题，则返回对应题 id
- `clarification_question_title`
  - 面向响应层的题目标题，若无法确定则为 `null`
- `clarification_kind`
  - 澄清类别，例如题目未识别、题已识别但选项未识别、partial 缺字段等

## `NonContentDetectOutput`

```json
{
  "non_content_mode": "control",
  "control_action": "next",
  "pullback_reason": null
}
```

字段说明：

- `non_content_mode`
  - `"control"` | `"pullback"`
- `control_action`
  - `"next"` | `"skip"` | `"undo"` | `"view_all"` | `"modify_previous"` | `null`
- `pullback_reason`
  - pullback 简短原因，若不是 pullback 则为 `null`

## `FinalAttributionOutput`

```json
{
  "winner_question_id": "question-02",
  "needs_clarification": false,
  "reason": "regular schedule is a better match than relaxed schedule"
}
```

字段说明：

- `winner_question_id`
  - 必须来自输入给定的候选集合
- `needs_clarification`
  - 若无法稳定唯一归属则为 `true`
- `reason`
  - 简短归属理由

## `MappedOptionResult`

```json
{
  "selected_options": ["B"],
  "confidence": 0.91,
  "reason": "spoken duration maps to the 10-15 minutes option"
}
```

字段说明：

- `selected_options`
  - 选项 id 数组
- `confidence`
  - `0.0 ~ 1.0`
- `reason`
  - 简短映射理由

## `ResponseComposerOutput`

```json
{
  "assistant_message": "已记录你的作息，接下来请回答下一题。"
}
```

字段说明：

- `assistant_message`
  - 唯一用户可见输出文本

### Response Output Rule

- `ResponseComposerOutput` 不得新增第二个用户可见字段。
- 若需要补充结构化事实，应由上游节点提供，不应由回复节点扩展输出形状。

## Invalid Output Examples

以下都视为非法：

- 包含 ```json 围栏
- 先写“以下是结果：”再给 JSON
- 输出不存在的枚举值
- 在 `FinalAttributionOutput` 中修改 `action_mode`
- 在 `ResponseComposerOutput` 中返回多个候选回复
