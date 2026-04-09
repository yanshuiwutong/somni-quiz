# somni-graph-quiz gRPC 接口文档

## 1. 文档定位

本文档只描述当前仓库中已经实现的 gRPC adapter 行为，以 [somni_quiz.proto](/G:/somni/somni-graph-quiz/proto/somni_quiz.proto) 与当前 service/mapper 实现为准，不覆盖历史老项目约定，也不把未实现的目标态能力写成现状。

当前实现特点：

- 使用 `somni.quiz.v1.QuizService`
- 提供两个 RPC：
  - `InitQuiz`
  - `ChatQuiz`
- 运行态为进程内内存会话
- 适配层默认按 `dynamic` 方式工作
- `InitQuiz` 对同一进程内已存在的 `session_id` 会优先恢复当前内存会话
- `InitQuizRequest.answer_record` 当前保留在 proto 中，但 adapter 不使用它做恢复初始化
- `ChatQuizRequest` 同时传 `message` 和 `direct_answer` 时，当前实现优先走 `direct_answer`
- `ChatQuizResponse.answer_status_code` 显式返回本轮记录状态
- `InitQuizResponse.progress_percent` 与 `ChatQuizResponse.progress_percent` 显式返回当前答题进度百分比
- `InitQuizRequest.default_city` 可为当前会话提供默认天气查询城市；未传时不再回退固定城市
- 天气查询当前按 `non_content` 处理，不进入答题记录与进度计算链路

## 2. 服务信息

| 项 | 值 |
| --- | --- |
| 协议 | `gRPC over HTTP/2` |
| 连接方式 | `plaintext` |
| Proto 文件 | [somni_quiz.proto](/G:/somni/somni-graph-quiz/proto/somni_quiz.proto) |
| Package | `somni.quiz.v1` |
| Service | `QuizService` |
| 方法 | `InitQuiz`、`ChatQuiz` |
| 本地默认监听地址 | `0.0.0.0:19000` |

补充说明：

- 本地默认地址来自 [settings.py](/G:/somni/somni-graph-quiz/src/somni_graph_quiz/app/settings.py) 中的 `SOMNI_GRPC_HOST` / `SOMNI_GRPC_PORT`
- 部署时可通过环境变量覆盖
- 当前服务器部署地址为 `43.138.100.224:18000`

## 3. 调用流程

标准调用顺序：

1. 调用 `InitQuiz`
2. 服务端根据 `session_id` 判断是否恢复已有内存会话；若不存在则根据 `questionnaire` 创建新会话
3. 循环调用 `ChatQuiz`
4. 每轮返回最新 `answer_record`、`answer_status_code`、`progress_percent` 和下一题
5. 当 `finalized=true` 时，响应中返回 `final_result`

当前限制：

- 会话只保存在 gRPC 服务进程内存中
- 服务重启后，`session_id` 对应状态不会自动恢复
- `InitQuiz` 当前不会消费请求里的 `answer_record` 来恢复历史进度

## 4. 当前实现的关键约束

- `quiz_mode` 在 `InitQuiz` 中可省略；省略时当前实现按 `dynamic` 处理
- `questionnaire` 由调用方完整提供，adapter 会将其映射为 runtime 题库
- `question_id` 应保持唯一；当前 adapter 不额外做重复 ID 保护
- `PendingQuestion.qid` 当前直接等于 `question_id`
- `InitQuizResponse.assistant_message` 新会话时通常等于首个 `pending_question.title`；恢复会话时与当前会话状态对齐
- `ChatQuiz` 可以走两种输入：
  - `message`
  - `direct_answer`
- 如果 `direct_answer` 存在，adapter 当前不会再读取 `message`
- `ChatQuizResponse.assistant_message` 是运行时生成的自然语言文案，不应把具体文本当成强契约
- `final_result` 只在完成态返回，当前最小保证结构为：
  - `completion_message`
  - `finalized`

## 5. 接口定义

### 5.1 InitQuiz

#### 5.1.1 作用

`InitQuiz` 用于创建新的内存会话，或恢复当前进程内已存在的会话，并返回当前待答题。

#### 5.1.2 请求字段

| 字段 | 类型 | 必填 | 当前实现说明 |
| --- | --- | --- | --- |
| `session_id` | `string` | 是 | 会话主键，由调用方维护 |
| `language` | `string` | 否 | 为空时使用 `zh-CN` |
| `questionnaire` | `repeated BusinessQuestion` | 是 | 当前题库定义来源 |
| `answer_record` | `AnswerRecord` | 否 | proto 保留字段；当前 adapter 不用于恢复 |
| `quiz_mode` | `string` | 否 | 为空时按 `dynamic` 处理 |
| `default_city` | `string` | 否 | 会话级默认天气城市；为空时表示当前会话没有默认城市 |

#### 5.1.3 服务端处理

当前 `InitQuiz` 的实际处理逻辑：

1. 若当前进程内已存在同一 `session_id`，直接恢复该会话当前 `graph_state`
2. 若当前进程内不存在该 `session_id`：
   - 将 `questionnaire` 映射为内部 `question_catalog`
   - 创建新的 `graph_state`，并写入 `default_city`
   - 挂载运行时依赖
   - 将会话保存在服务进程内存中
3. 返回当前会话的 `pending_question`、`answer_record` 与 `progress_percent`

当前不会做的事：

- 不读取请求 `answer_record` 恢复进度
- 不区分 `business_9` 与 `dynamic` 两套独立业务流
- 不返回复杂人格或评分结果

#### 5.1.4 响应字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | `bool` | 成功时为 `true` |
| `session_id` | `string` | 当前会话 ID |
| `initialized` | `bool` | 成功初始化时为 `true` |
| `assistant_message` | `string` | 新会话时通常等于首题标题；恢复会话时对齐当前待答题或完成态兜底文案 |
| `pending_question` | `PendingQuestion` | 当前待答题；完成态时可能为空 |
| `answer_record` | `AnswerRecord` | 当前答卷快照；新会话通常为空，恢复会话时返回已有记录 |
| `quiz_mode` | `string` | 回显当前会话模式 |
| `progress_percent` | `double` | 当前答题进度百分比；新会话通常为 `0.0`，恢复会话时为当前进度 |

### 5.2 ChatQuiz

#### 5.2.1 作用

`ChatQuiz` 用于提交本轮输入、驱动 runtime 执行一轮问答，并返回：

- 最新答卷快照
- 本轮记录状态
- 当前答题进度
- 下一题
- 完成态结果

#### 5.2.2 请求字段

| 字段 | 类型 | 必填 | 当前实现说明 |
| --- | --- | --- | --- |
| `session_id` | `string` | 是 | 必须先通过 `InitQuiz` 建立 |
| `message` | `string` | 条件必填 | 当没有 `direct_answer` 时使用 |
| `direct_answer` | `DirectAnswer` | 条件必填 | 若存在则优先使用 |

#### 5.2.3 输入模式

模式 A：`message`

- 适合自然语言输入
- adapter 会将其转换为 `TurnInput(input_mode="message")`

模式 B：`direct_answer`

- 适合调用方已经拿到结构化答案的场景
- adapter 会将其转换为 `TurnInput(input_mode="direct_answer")`
- 当前 `raw_input` 生成规则为：
  - 优先 `direct_answer.input_value`
  - 否则将 `selected_options` 用空格拼接

#### 5.2.4 响应字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | `bool` | 成功时为 `true` |
| `session_id` | `string` | 当前会话 ID |
| `assistant_message` | `string` | 本轮回复文案；文本内容依赖运行时状态与 LLM/规则路径 |
| `pending_question` | `PendingQuestion` | 下一题；完成态或无待答题时为空 message |
| `finalized` | `bool` | 是否完成 |
| `answer_record` | `AnswerRecord` | 最新答卷快照 |
| `final_result` | `Struct` | 完成态结果；未完成时通常为空 `Struct` |
| `quiz_mode` | `string` | 会话模式回显 |
| `answer_status_code` | `string` | 本轮答题记录状态码 |
| `progress_percent` | `double` | 当前答题进度百分比 |

补充说明：

- 当前 `ChatQuiz` 支持天气类自然语言输入，例如 `今天天气怎么样`
- 天气查询按 `non_content` 处理
- 天气文案按“LLM 优先、固定模板兜底”生成，语言跟随会话 `language`
- 天气查询成功后会把天气结果写进 `assistant_message`，同时继续返回当前待答题
- 天气查询缺少城市时，会先在 `assistant_message` 中追问城市，本轮不拉回问卷
- 天气查询回合不会写入 `answer_record`
- 天气查询回合的 `answer_status_code` 为 `NOT_RECORDED`
- 天气查询回合的 `progress_percent` 不变化

#### 5.2.5 `answer_status_code` 取值

当前 adapter 会根据本轮 `recent_turns` 最后一条 turn metadata 推导 `answer_status_code`。

| 值 | 含义 |
| --- | --- |
| `RECORDED` | 本轮成功记录了新的答案 |
| `UPDATED` | 本轮修改了既有答案，或执行了撤回后状态发生更新 |
| `PARTIAL` | 本轮只记录了部分结构化答案，仍需补充 |
| `NOT_RECORDED` | 本轮未形成有效记录 |

当前实现细节：

- 优先读取：
  - `partial_question_ids`
  - `modified_question_ids`
  - `recorded_question_ids`
- 若上面三类 metadata 都为空，则继续参考 `turn_outcome`
- 当缺少可识别的 turn metadata / `turn_outcome` 时，返回 `NOT_RECORDED`

#### 5.2.6 `progress_percent` 计算规则

`progress_percent` 表示整份问卷当前完成百分比，计算规则为：

- 完整答完 1 题记为 `1.0`
- `partial` 题记为 `0.5`
- 已完整记录的题不会再重复计 partial
- 返回值为 `(完整题数 + partial * 0.5) / 总题数 * 100`
- 当 `finalized=true` 时固定返回 `100.0`
- 当总题数小于等于 0 时返回 `0.0`

#### 5.2.7 未初始化会话的失败返回

若调用方未先执行 `InitQuiz` 就直接调用 `ChatQuiz`，当前 adapter 会：

- 设置 gRPC 状态码为 `FAILED_PRECONDITION`
- 返回一个业务响应体，而不是抛出空响应

当前明确保证的响应特征：

| 字段 | 值 |
| --- | --- |
| `success` | `false` |
| `session_id` | 请求中的 `session_id` |
| `assistant_message` | `Session not initialized. Call InitQuiz first.` |
| `answer_status_code` | `NOT_RECORDED` |

说明：

- 其他未显式赋值的 proto 字段在不同客户端序列化视图中可能表现为默认值或被省略

## 6. 公共类型说明

### 6.1 BusinessQuestion

`BusinessQuestion` 是接入方向 adapter 提供的题目定义。当前 adapter 主要消费这些字段：

| 字段 | 当前用途 |
| --- | --- |
| `question_id` | 题目唯一标识 |
| `title` | 题目标题 |
| `description` | 题目描述 |
| `input_type` | 题型，例如 `text`、`radio`、`time_range` |
| `tags` | 写入题目 metadata 的 `matching_hints` |
| `options` | 选项列表 |
| `config` | 透传到 `PendingQuestion.config` |

当前 proto 中这些字段会被保留，但 adapter 不直接使用：

- `scoring_type`
- `dimension`
- `business_type`
- `language`
- `status`
- `is_extra_input`

### 6.2 BusinessOption

当前 adapter 主要消费这些字段：

| 字段 | 当前用途 |
| --- | --- |
| `option_id` | 业务选项 ID |
| `option_text` | 选项显示文本 |
| `label_value` | 单个 alias，映射到内部 `aliases` |

当前 proto 中这些字段会被保留，但 adapter 不直接使用：

- `score`
- `sort_order`
- `is_input_enabled`

### 6.3 PendingQuestion

`PendingQuestion` 是服务端返回给调用方的当前待答题。

当前 adapter 返回规则：

- `question_id`：来自当前待答题
- `qid`：当前直接等于 `question_id`
- `title / input_type / tags / options / config`：来自当前题目定义

### 6.4 PendingQuestionConfig

当前 adapter 会透传题目配置，典型场景是 `time_range` 题的多字段输入提示。

例如：

```json
{
  "items": [
    {"index": 0, "label": "上床时间：", "format": "HH:mm"},
    {"index": 1, "label": "起床时间：", "format": "HH:mm"}
  ]
}
```

### 6.5 AnswerRecord / AnswerItem

`answer_record` 是当前答卷快照。`ChatQuiz` 每轮都会返回完整快照。

`AnswerItem` 当前由 runtime 的记录结果映射而来：

- `question_id`
- `value`
- `direct_answer`

新建会话时 `InitQuiz` 当前通常返回空答卷：

```json
{
  "answer_id": "",
  "answers": []
}
```

### 6.6 AnswerValue

当前 adapter 的映射规则如下：

| 字段 | 来源 |
| --- | --- |
| `option_codes` | 直接来自记录中的 `selected_options` |
| `bedtime` | 来自记录中的 `field_updates.bedtime` |
| `wake_time` | 来自记录中的 `field_updates.wake_time` |
| `score` | 当前 adapter 不主动写入 |

注意：

- 当前响应里的 `option_codes` 直接复用已记录的业务选项 ID
- 当前 adapter 不区分“内部标准 code”和“业务 option_id”两套返回值
- 文本题没有独立 `value.text` 字段；文本内容保存在 `direct_answer.input_value`

### 6.7 DirectAnswer

`DirectAnswer` 既是 `ChatQuiz` 的结构化输入，也是响应中的结构化视图。

| 字段 | 说明 |
| --- | --- |
| `question_id` | 题目 ID |
| `selected_options` | 结构化选项答案 |
| `input_value` | 自由输入或结构化字符串 |

推荐用法：

- 单选题：
  - `selected_options` 填业务选项 ID
  - `input_value` 留空
- 时间题：
  - `input_value` 填类似 `23:00-07:00` 的字符串
  - 如无必要，`selected_options` 留空
- 文本题：
  - `input_value` 填原始文本

## 7. 示例

以下示例基于当前实现编写。

说明：

- 字段形状以 proto 和 adapter 为准
- 示例使用的是“JSON 形态的 protobuf 视图”
- 不同客户端对默认值字段可能显示为空对象、默认值，或直接省略
- `assistant_message` 为示意文案，真实文本可能因运行时状态和 LLM 可用性而变化

### 7.1 InitQuiz 最小请求

```json
{
  "session_id": "session-1",
  "language": "zh-CN",
  "quiz_mode": "dynamic",
  "default_city": "北京",
  "questionnaire": [
    {
      "question_id": "question-01",
      "title": "年龄段",
      "input_type": "text"
    },
    {
      "question_id": "question-02",
      "title": "平时作息",
      "input_type": "time_range",
      "config": {
        "items": [
          {"index": 0, "label": "上床时间：", "format": "HH:mm"},
          {"index": 1, "label": "起床时间：", "format": "HH:mm"}
        ]
      }
    }
  ],
  "answer_record": {
    "answer_id": "ignored-by-current-adapter",
    "answers": []
  }
}
```

### 7.2 InitQuiz 最小响应

```json
{
  "success": true,
  "session_id": "session-1",
  "initialized": true,
  "assistant_message": "年龄段",
  "pending_question": {
    "question_id": "question-01",
    "qid": "question-01",
    "title": "年龄段",
    "input_type": "text",
    "tags": [],
    "options": [],
    "config": {}
  },
  "answer_record": {
    "answer_id": "",
    "answers": []
  },
  "quiz_mode": "dynamic",
  "progress_percent": 0.0
}
```

### 7.3 ChatQuiz 自然语言输入请求

```json
{
  "session_id": "session-1",
  "message": "22"
}
```

### 7.4 ChatQuiz 未完成态响应

```json
{
  "success": true,
  "session_id": "session-1",
  "assistant_message": "已记录本轮答案，请继续回答下一题。",
  "pending_question": {
    "question_id": "question-02",
    "qid": "question-02",
    "title": "平时作息",
    "input_type": "time_range",
    "tags": [],
    "options": [],
    "config": {
      "items": [
        {"index": 0, "label": "上床时间：", "format": "HH:mm"},
        {"index": 1, "label": "起床时间：", "format": "HH:mm"}
      ]
    }
  },
  "finalized": false,
  "answer_record": {
    "answer_id": "",
    "answers": [
      {
        "question_id": "question-01",
        "value": {
          "option_codes": []
        },
        "direct_answer": {
          "question_id": "question-01",
          "selected_options": [],
          "input_value": "22"
        }
      }
    ]
  },
  "final_result": {},
  "quiz_mode": "dynamic",
  "answer_status_code": "RECORDED",
  "progress_percent": 50.0
}
```

### 7.5 ChatQuiz 结构化直答请求

```json
{
  "session_id": "session-1",
  "direct_answer": {
    "question_id": "question-02",
    "selected_options": [],
    "input_value": "23:00-07:00"
  }
}
```

### 7.6 ChatQuiz 完成态响应

```json
{
  "success": true,
  "session_id": "session-1",
  "assistant_message": "感谢你的分享，我已经记录完成。",
  "pending_question": {},
  "finalized": true,
  "answer_record": {
    "answer_id": "",
    "answers": [
      {
        "question_id": "question-01",
        "value": {
          "option_codes": []
        },
        "direct_answer": {
          "question_id": "question-01",
          "selected_options": [],
          "input_value": "22"
        }
      },
      {
        "question_id": "question-02",
        "value": {
          "option_codes": [],
          "bedtime": "23:00",
          "wake_time": "07:00"
        },
        "direct_answer": {
          "question_id": "question-02",
          "selected_options": [],
          "input_value": "23:00-07:00"
        }
      }
    ]
  },
  "final_result": {
    "completion_message": "感谢你的分享，我已经记录完成。",
    "finalized": true
  },
  "quiz_mode": "dynamic",
  "answer_status_code": "RECORDED",
  "progress_percent": 100.0
}
```

### 7.7 ChatQuiz 天气查询响应

```json
{
  "success": true,
  "session_id": "session-1",
  "assistant_message": "北京今天天气：晴，22C。我们继续回答年龄段。",
  "pending_question": {
    "question_id": "question-01",
    "qid": "question-01",
    "title": "年龄段",
    "input_type": "text",
    "tags": [],
    "options": [],
    "config": {}
  },
  "finalized": false,
  "answer_record": {
    "answer_id": "",
    "answers": []
  },
  "final_result": {},
  "quiz_mode": "dynamic",
  "answer_status_code": "NOT_RECORDED",
  "progress_percent": 0.0
}
```

说明：

- 若用户消息里显式给了城市，则优先使用用户显式城市
- 若用户消息里未显式给城市，则尝试使用 `InitQuizRequest.default_city`
- 若没有可用城市，当前实现会在 `assistant_message` 中追问城市
- 当前版本只支持“今天天气 / 当前天气”这一类天气查询

### 7.8 ChatQuiz 未初始化会话响应

```json
{
  "success": false,
  "session_id": "missing-session",
  "assistant_message": "Session not initialized. Call InitQuiz first.",
  "pending_question": {},
  "finalized": false,
  "answer_record": {
    "answer_id": "",
    "answers": []
  },
  "final_result": {},
  "quiz_mode": "",
  "answer_status_code": "NOT_RECORDED",
  "progress_percent": 0.0
}
```

## 8. 当前未实现或不应误解的能力

以下内容不要按“当前可用能力”理解：

- `InitQuiz(answer_record=...)` 恢复历史答卷
- `business_9` 独立业务流
- `PendingQuestion.qid = Q01/Q02/...`
- 完成态返回复杂 `persona / plan.stages` 结构
- 比 `FAILED_PRECONDITION` 更完整的统一错误包装协议

这些字段或概念有的仍保留在 proto 中，但当前 adapter 并未实现对应行为。

## 9. 常见问题

### 为什么必须先调 `InitQuiz`？

因为 `ChatQuiz` 依赖服务端内存中的会话快照。当前 adapter 不会在 `ChatQuiz` 中自动创建会话。

如果跳过这一步，当前会返回：

- gRPC 状态：`FAILED_PRECONDITION`
- 业务字段：`success=false`
- `answer_status_code=NOT_RECORDED`

### `InitQuizRequest.answer_record` 为什么没有生效？

因为这个字段当前仅保留在 proto 里，adapter 还没有实现基于它的恢复初始化逻辑。

### `default_city` 有什么作用？

它是当前会话的默认天气城市，只影响天气查询类输入，不影响问卷答题逻辑。

如果用户在天气消息里显式给了城市，则以用户显式城市为准；如果没有显式城市，则尝试使用 `default_city`；如果仍然没有可用城市，则会先追问城市。

### 为什么 `assistant_message` 可能和示例不同？

因为 `assistant_message` 是运行时生成文案。`InitQuiz` 阶段当前通常等于首题标题，而 `ChatQuiz` 阶段会根据当前题目、记录结果以及 LLM/规则路径生成文本，所以不应把具体措辞当成强契约。

### `answer_status_code` 应该怎么理解？

可以按“本轮记录结果”理解，而不是“整份问卷总体状态”：

- `RECORDED`：本轮记下了答案
- `UPDATED`：本轮改了旧答案，或执行撤回后状态发生更新
- `PARTIAL`：本轮只记下部分结构化字段
- `NOT_RECORDED`：本轮没有形成有效记录

### `progress_percent` 应该怎么理解？

可以按“整份问卷当前完成百分比”理解：

- 完整答完 1 题记为 `1.0` 题
- `partial` 题记为 `0.5` 题
- 返回值为 `(完整题数 + partial * 0.5) / 总题数 * 100`
- 问卷全部完成后固定返回 `100.0`

### 服务重启后怎么继续？

当前 adapter 是进程内内存态。

- 同一服务进程内，重复调用同一 `session_id` 的 `InitQuiz` 可以恢复该会话
- 服务重启后，会话仍会丢失，需要重新调用 `InitQuiz` 建立新会话
