# Glossary

## Goal

统一 `somni-graph-quiz` 所有 prompt 中使用的核心术语，避免同一概念在不同节点中出现不同名字或不同语义。

## Terms

### `main_branch`

当前轮进入的主分支，只允许：

- `non_content`
- `content`

同一轮不能同时执行两个主分支。

### `non_content`

不直接用于回答或修改问卷内容的输入，包括：

- 控制动作
- 拉回类输入

### `content`

用于回答问卷、补全 partial、或修改已答题的输入域。

### `action_mode`

`content` 域中单个内容单元的动作类型，只允许：

- `answer`
- `modify`
- `partial_completion`

### `answer`

用户在回答一个此前未完成的问题，或重新回答一个被跳过但未完成的问题。

### `modify`

用户再次命中一个已完整回答的问题，本轮应视为修改，而不是新增回答。

### `partial_completion`

用户正在补一个此前处于 partial 状态的问题的缺失字段。

### `ContentUnit`

从一条 `content` 输入中切出的、可独立对应一次答题或修改意图的最小语义单元。

### `candidate_question_ids`

某个 `ContentUnit` 当前可能归属的问题 id 集合。

### `winner_question_id`

某个 `ContentUnit` 最终归属的问题 id。

### `needs_attribution`

表示当前单元还不能稳定唯一归属，需要交给归属裁决节点继续判断。

### `clarification_context`

上一轮因信息不足而要求澄清时，为下一轮补充输入保留的上下文。

### `answered_records`

只存完整已记录答案的运行态结构。

### `pending_partial_answers`

只存 partial 答案的运行态结构，不与完整答案混存。

### `skipped_question_ids`

被显式跳过或因两次无效自动跳过的问题集合。`skipped` 不等于完成。

### `response_language`

本轮最终回复使用的语言。默认继承 `session.language_preference`，可在本轮覆盖，但不直接回写长期会话配置。

### `Somni persona`

`response_composer` 在用户可见回复中必须维持的稳定人格：温柔、治愈、自然、松弛，同时对问卷流程保持温柔的坚定感。

### `gentle pullback`

面对闲聊、跑题、拒答或情绪表达时，先极简接住，再立刻把对话温柔但坚定地拉回睡眠问卷。

### `safety boundary`

用户可见回复不得越过的边界，包括：不诊断、不制造焦虑、不推销、不暴露内部调试信息、不编造业务真相。

### `pullback`

`turn_outcome` 之一，表示本轮主要结果是把闲聊、无效或跑题输入拉回问卷流程。

### `partial_recorded`

`turn_outcome` 之一，表示只记录了部分答案，本轮要继续追问剩余缺失字段。

### `undo_applied`

`turn_outcome` 之一，表示本轮已执行撤回或回退动作。

### `view_only`

`turn_outcome` 之一，表示本轮主要在查看记录、进度或历史，不推进新的内容答题。

## Usage Rules

- 所有 prompt 必须使用这里定义的术语名。
- 不允许在单个 prompt 内发明同义词替代核心字段。
- 若新增状态字段影响 prompt 交互，先补本文件，再补输出契约。
