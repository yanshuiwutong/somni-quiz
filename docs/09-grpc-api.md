# somni-graph-quiz gRPC 接口文档

## 1. 文档定位

本文档只描述当前仓库里已经实现的 gRPC adapter 行为，不覆盖历史老项目接口约定，也不把尚未实现的目标态能力写成现状。

当前实现特点：

- 使用 [somni_quiz.proto](/G:/somni/somni-graph-quiz/proto/somni_quiz.proto) 定义 `somni.quiz.v1.QuizService`
- 提供两个 RPC：
  - `InitQuiz`
  - `ChatQuiz`
- 运行态为进程内内存会话
- 适配层默认按 `dynamic` 方式工作
- `InitQuizRequest.answer_record` 当前保留在 proto 中，但 adapter 不使用它做恢复初始化
- `ChatQuizRequest` 同时传 `message` 和 `direct_answer` 时，当前实现优先走 `direct_answer`

## 2. 服务信息

| 项 | 值 |
| --- | --- |
| 协议 | `gRPC over HTTP/2` |
| 连接方式 | `plaintext` |
| Proto 文件 | [somni_quiz.proto](/G:/somni/somni-graph-quiz/proto/somni_quiz.proto) |
| Package | `somni.quiz.v1` |
| Service | `QuizService` |
| 方法 | `InitQuiz`、`ChatQuiz` |
| 默认监听地址 | `0.0.0.0:19000` |

默认监听地址来自 [settings.py](/G:/somni/somni-graph-quiz/src/somni_graph_quiz/app/settings.py)：

- `SOMNI_GRPC_HOST`
- `SOMNI_GRPC_PORT`

## 3. 调用流程

标准调用顺序：

1. 调用 `InitQuiz`
2. 服务端根据 `questionnaire` 创建会话，返回第一道待答题
3. 循环调用 `ChatQuiz`
4. 每轮返回最新 `answer_record` 和下一题
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
- `InitQuizResponse.assistant_message` 当前直接使用首个 `pending_question.title`
- `ChatQuiz` 可以走两种输入：
  - `message`
  - `direct_answer`
- 如果 `direct_answer` 存在，adapter 当前不会再读取 `message`
- `final_result` 只在完成态返回，当前最小保证结构为：
  - `completion_message`
  - `finalized`

## 5. 接口定义

### 5.1 InitQuiz

#### 5.1.1 作用

`InitQuiz` 用于创建一个新的内存会话，并返回当前第一道待答题。

#### 5.1.2 请求字段

| 字段 | 类型 | 必填 | 当前实现说明 |
| --- | --- | --- | --- |
| `session_id` | `string` | 是 | 会话主键，由调用方维护 |
| `language` | `string` | 否 | 为空时使用 `zh-CN` |
| `questionnaire` | `repeated BusinessQuestion` | 是 | 当前题库定义来源 |
| `answer_record` | `AnswerRecord` | 否 | proto 保留字段；当前 adapter 不用于恢复 |
| `quiz_mode` | `string` | 否 | 为空时按 `dynamic` 处理 |

#### 5.1.3 服务端处理

当前 `InitQuiz` 的实际处理逻辑：

1. 将 `questionnaire` 映射为内部 `question_catalog`
2. 创建新的 `graph_state`
3. 挂载 LLM 依赖
4. 将会话保存在服务进程内存中
5. 返回 `questionnaire` 中第一道题作为 `pending_question`

当前不会做的事：

- 不读取请求 `answer_record` 恢复进度
- 不区分 `business_9` 与 `dynamic` 两套业务流程
- 不返回复杂人格或评分结果

#### 5.1.4 响应字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | `bool` | 成功时为 `true` |
| `session_id` | `string` | 当前会话 ID |
| `initialized` | `bool` | 成功初始化时为 `true` |
| `assistant_message` | `string` | 当前实现等于首题标题 |
| `pending_question` | `PendingQuestion` | 第一题 |
| `answer_record` | `AnswerRecord` | 当前固定返回空答卷 |
| `quiz_mode` | `string` | 回显当前会话模式 |

### 5.2 ChatQuiz

#### 5.2.1 作用

`ChatQuiz` 用于提交本轮输入、驱动 runtime 执行一轮问答，并返回：

- 最新答卷快照
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
| `assistant_message` | `string` | 本轮回复文案；启用远端 LLM 时文本可能变化 |
| `pending_question` | `PendingQuestion` | 下一题；完成态时为空对象 |
| `finalized` | `bool` | 是否完成 |
| `answer_record` | `AnswerRecord` | 最新答卷快照 |
| `final_result` | `Struct` | 完成态结果；未完成时为空 |
| `quiz_mode` | `string` | 会话模式回显 |

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

`InitQuiz` 当前固定返回空答卷：

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

- 当前响应里的 `option_codes` 直接复用已记录的选项 ID
- 当前 adapter 不再区分“内部标准 code”和“业务 option_id”两套返回值
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
- `assistant_message` 在启用远端 LLM 时可能与示例不同
- 下面的示例按“未启用远端 LLM”的回退路径展示

### 7.1 InitQuiz 最小请求

```json
{
  "session_id": "session-1",
  "language": "zh-CN",
  "quiz_mode": "dynamic",
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
  "quiz_mode": "dynamic"
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
  "assistant_message": "已记录，我们继续回答下一题：平时作息。",
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
  "quiz_mode": "dynamic"
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
  "assistant_message": "感谢你的分享。我已经大致了解了你的睡眠习惯，接下来会结合你记录下来的作息与感受，为你整理更适合你的专属声、光、香睡眠方案。",
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
    "completion_message": "感谢你的分享。我已经大致了解了你的睡眠习惯，接下来会结合你记录下来的作息与感受，为你整理更适合你的专属声、光、香睡眠方案。",
    "finalized": true
  },
  "quiz_mode": "dynamic"
}
```

## 8. 当前未实现或不应误解的能力

以下内容不要按“当前可用能力”理解：

- `InitQuiz(answer_record=...)` 恢复历史答卷
- `business_9` 独立业务流
- `PendingQuestion.qid = Q01/Q02/...`
- 完成态返回复杂 `persona / plan.stages` 结构
- 统一规范化的 gRPC 错误码封装

这些字段或概念有的仍保留在 proto 中，但当前 adapter 并未实现对应行为。

## 9. 常见问题

### 为什么必须先调 `InitQuiz`？

因为 `ChatQuiz` 依赖服务端内存中的会话快照。当前 adapter 不会在 `ChatQuiz` 中自动创建会话。

### `InitQuizRequest.answer_record` 为什么没有生效？

因为这个字段当前仅保留在 proto 里，adapter 还没有实现基于它的恢复初始化逻辑。

### 为什么 `assistant_message` 可能和示例不同？

因为当远端 LLM 可用时，响应层会优先走 LLM 文案生成；示例展示的是无远端 LLM 时的回退文案。

### 服务重启后怎么继续？

当前 adapter 是进程内内存态。服务重启后，会话会丢失，需要重新调用 `InitQuiz` 建立新会话。
