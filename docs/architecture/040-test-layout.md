# Test Layout

> 文档即接口。本文件定义 `somni-graph-quiz` 的测试分层、目录结构、夹具组织与回归策略。状态模型与节点图以前置文档 [010-state-model.md](./010-state-model.md)、[020-node-graph.md](./020-node-graph.md)、[030-prompt-layout.md](./030-prompt-layout.md) 为准。

## Goal

定义新项目的测试架构，使其在不依赖真实公网和真实在线 LLM 的前提下，仍能稳定验证以下目标：

- gRPC 输入输出格式保持不变
- streamlit 与 grpc 共享同一 graph runtime
- 主分支互斥：`non_content | content`
- `content` 域内支持 `answer + modify + partial_completion` 混合命中
- 已答题再次命中视为修改
- 单片段时间表达、多题候选冲突、partial 补全与跳过等复杂场景可持续回归
- LLM 主判定链路与无网规则兜底都可单独验证

## Core Principles

- 测试优先验证结构化状态与流程结果，不把自然语言回复全文当作主要断言对象。
- 默认测试套件不依赖真实公网，不依赖真实模型，不跑公网黑盒回归。
- 来自历史真实样例的场景要转成本地结构化语义回归用例，而不是 brittle goldens。
- 节点测试聚焦节点职责边界，运行时集成测试聚焦状态流转，适配层测试聚焦接口兼容。
- 每一层测试都必须能定位失败责任，不允许所有问题都挤到“端到端大测”里。

## Test Directory Layout

固定目录如下：

```text
tests/
  conftest.py
  unit/
    contracts/
    domain/
    llm/
    nodes/
      layer1/
      layer2/
      layer3/
    runtime/
  integration/
    runtime/
    adapters/
      grpc/
      streamlit/
  regression/
    fixtures/
    content_cases/
    grpc/
    streamlit/
```

## Test Layers

测试固定分为四层：

1. `contract tests`
2. `node tests`
3. `runtime integration tests`
4. `adapter regression tests`

这四层之外，可补充少量 `domain` 和 `llm` 单元测试，但仍服务于四层目标。

## Layer 1: Contract Tests

位置：

- `tests/unit/contracts/`

### Responsibility

验证静态接口契约是否稳定，包括：

- `GraphState` 顶层结构
- `SessionMemory` / `TurnContext` / `ArtifactsState` 字段形状
- `BranchResult` 统一输出形状
- `FinalizedTurnContext` 形状
- prompt 输出 JSON 契约
- grpc adapter 对外输入输出 DTO 映射形状

### Typical Assertions

- 必填字段存在
- 枚举值受限
- `partial_completion` 仅作为内部动作存在
- `skipped` 不等于 `completed`
- `ResponseComposerNode` 输出只有 `assistant_message`
- grpc response 字段与旧接口兼容

### Why This Layer Exists

接口漂移会让 graph、adapter、prompt 三边同时出错。契约测试必须最先报错。

## Layer 2: Node Tests

位置：

- `tests/unit/nodes/layer1/`
- `tests/unit/nodes/layer2/`
- `tests/unit/nodes/layer3/`

### Responsibility

逐节点验证职责边界，确保每个节点“只做自己该做的事”。

### Layer 1 Node Tests

重点覆盖：

- `TurnClassifyNode` 识别 `non_content | content`
- `TurnClassifyNode` 读取完整 `llm_memory_view`
- 控制语句、闲聊、内容输入的主分支判定
- LLM 不可用时的规则兜底

### Layer 2 Node Tests

重点覆盖：

- `ContentUnderstand` 的内容单元切分
- `action_mode = answer | modify | partial_completion`
- 候选题集合输出
- `needs_attribution` 标记
- `FinalAttribution` 只在候选集合内选择 winner
- `text_option_mapping` 的口语选项映射
- `NonContentBranch` 的控制动作和 pullback 结果
- `ContentApply` 的 patch 解释与提交规则

### Layer 3 Node Tests

重点覆盖：

- `TurnFinalizeNode` 的 next question priority
- attempt count 与自动跳过
- partial follow-up / partial skip
- completed 判定
- `ResponseComposerNode` 的多语言输出
- 唯一响应节点原则

### Node Test Rules

- 使用 fake LLM 或固定 stub 输出。
- 不直接依赖外部模型。
- 每个测试文件尽量只覆盖一个节点或一个节点内部子阶段。
- 若测试关注 `FinalAttribution`，只断言归属裁决，不顺带断言状态落库。

## Layer 3: Runtime Integration Tests

位置：

- `tests/integration/runtime/`

### Responsibility

在不经过 grpc/streamlit 适配层的前提下，直接验证 graph runtime 的单轮和多轮流转。

### Must Cover

- 正常答题推进下一题
- 已答题再次命中转修改
- `content` 域内多单元并行命中
- 普通作息与自由放松作息候选冲突
- 单片段时间进入 partial
- partial 补全成功
- partial 两次无效后跳过但保留 partial
- partial 被跳过后，后续补缺失字段可自动恢复
- 显式跳题与自动跳题
- `clarification_context` 下轮补充
- `language_preference` 影响响应语言

### What To Assert

优先断言：

- `updated_graph_state`
- `session_memory.question_states`
- `answered_records`
- `pending_partial_answers`
- `pending_question`
- `finalized`
- `turn_outcome`

谨慎断言：

- `assistant_message`

对于 `assistant_message`，只建议断言：

- 非空
- 对应语言
- 包含关键事实短语

不建议把整句回复做成易碎 golden。

## Layer 4: Adapter Regression Tests

位置：

- `tests/integration/adapters/grpc/`
- `tests/integration/adapters/streamlit/`
- `tests/regression/grpc/`
- `tests/regression/streamlit/`

### Responsibility

验证对外接口和 UI 接入层在重构后仍保持兼容。

### gRPC Must Cover

- 请求输入结构不变
- 响应输出结构不变
- `message` 入口
- `direct_answer` 入口
- `language_preference` 透传到响应层
- 多轮会话上下文延续

### Streamlit Must Cover

- 与同一 runtime 的状态同步
- 用户发送消息后的页面状态更新
- 下一题展示来源于统一 `pending_question`
- 记录展示与撤回显示一致

### Adapter Regression Rules

- 适配层回归重点看“接口兼容”，不是重复验证底层所有业务逻辑。
- 典型业务行为由 runtime integration 和 regression cases 覆盖。

## Regression Case Strategy

位置：

- `tests/regression/content_cases/`
- `tests/regression/fixtures/`

### Source of Cases

历史 `.docx` 中的真实样例，只作为“场景来源”，转写成本地结构化回归案例。

### Explicit Non-Goals

- 不做真实公网测试
- 不直接对真实在线模型跑回归
- 不把原始聊天全文与回复全文做 brittle golden

### Recommended Fixture Shape

每个回归用例建议采用结构化文件，例如 `yaml/json`：

```python
RegressionCase = {
    "case_id": str,
    "title": str,
    "turns": list[{
        "input_mode": "message" | "direct_answer",
        "raw_input": str,
        "direct_answer_payload": dict | None,
        "llm_stub_key": str | None,
    }],
    "expected": {
        "answered_question_ids": list[str],
        "modified_question_ids": list[str],
        "partial_question_ids": list[str],
        "pending_question_id": str | None,
        "clarification_needed": bool,
        "skipped_question_ids": list[str],
    },
}
```

### Why Structured Cases Instead of Goldens

因为新架构中最终回复由统一响应节点生成，文案可在保证功能不变的前提下调整。回归应锁定业务语义，而不是锁死每个字。

## Scenario Classes To Preserve

回归样例至少覆盖以下场景类：

1. `23点`、`那7左右` 这类语义不足表达需要澄清或裁决。
2. `23点睡` 应命中睡眠相关题，而不是同时命中自由入睡和起床两题。
3. `我22岁，每天11点睡觉，7点起床` 只应命中年龄题和常规作息题。
4. 已答题再次命中，应识别为修改。
5. `十来分钟` 这类口语表达需要映射到正确选项。
6. partial 场景下第二轮只补缺失字段。
7. partial 两次无效后自动跳过，但保留 partial。
8. partial 被 `跳过` 后，再输入缺失字段应恢复并补全，不应丢失之前那一半。
9. partial 被 `跳过` 后，若输入无关内容，不应错误抢回该 partial 题。
10. 显式 `下一题`、`跳过`、`撤回`、`查看全部`。
11. `改上一题` 这类依赖短期记忆的控制语句。
12. `language_preference` 切换下的最终响应语言。

## LLM Test Strategy

位置：

- `tests/unit/llm/`

### Responsibility

验证 LLM 客户端封装、输出解析、fallback 触发条件，而不是验证真实模型“聪不聪明”。

### Rules

- 使用 fake provider、stub provider 或本地录制响应。
- 重点验证：
  - JSON 解析
  - 超时处理
  - 不可解析输出处理
  - fallback_used 标识
- 不把真实在线模型调用纳入默认测试流水线。

## Domain and Runtime Utility Tests

位置：

- `tests/unit/domain/`
- `tests/unit/runtime/`

### Responsibility

验证不依赖 LLM 的纯状态逻辑，例如：

- `question_states` 转换
- partial 合并
- skipped partial 恢复补全
- attempt count 递增/重置
- skipped 重新进入答题
- `next question priority`
- patch merge 与撤回基线

这些测试是 runtime integration 之前的防线。

## Test Fixture Design

`tests/conftest.py` 应统一提供：

- 最小 `question_catalog`
- 可复用 `GraphState` builder
- fake LLM provider
- runtime factory
- grpc request/response builders
- streamlit session state builders

### Rules

- fixture 默认保持最小化，只包含当前测试必需字段。
- 复杂问卷场景通过工厂函数组合，不在每个测试里手写大字典。
- LLM stub 输出应按节点区分，避免一个全局魔法字符串污染所有测试。

## Suggested Naming Conventions

- `test_turn_classify_routes_control_to_non_content`
- `test_content_understand_marks_answered_question_as_modify`
- `test_final_attribution_prefers_regular_schedule_when_context_missing`
- `test_runtime_partial_followup_keeps_missing_fields`
- `test_grpc_contract_message_input_shape_unchanged`

命名应直接暴露场景、节点或契约意图。

## Failure Localization Rules

当一个场景失败时，应优先能定位到以下单层：

- 契约字段变更 -> `contract tests`
- 节点推断错误 -> `node tests`
- 状态流转错误 -> `runtime integration`
- 对外接口回归 -> `adapter regression`

若某问题只能靠最外层端到端测试发现，说明测试架构还不够细。

## CI Recommendation

默认流水线建议执行顺序：

1. `unit/contracts`
2. `unit/domain + unit/runtime`
3. `unit/nodes`
4. `integration/runtime`
5. `integration/adapters`
6. `regression`

### Rules

- 公网依赖必须为 `0`。
- 测试应支持本地离线运行。
- regression 可以比 unit 慢，但必须稳定可复现。

## Acceptance Criteria

本测试布局必须保证：

1. 新 graph runtime 重构后，grpc 接口逻辑与输入输出格式不变。
2. streamlit 与 grpc 共用一套业务内核，并有各自适配层回归。
3. LLM 不可用时，规则兜底路径有明确测试。
4. 已答题再命中修改、partial、跳题、撤回、查看记录等关键流转都有独立回归。
5. `.docx` 来源场景转成本地结构化语义回归，不依赖真实公网。
6. 回复文案可演进，但业务语义回归不会因措辞变化频繁误报。

## Non-Goals

- 不建立依赖真实在线模型的默认测试套件。
- 不使用真实公网样例直接做黑盒网络回归。
- 不用整句自然语言 golden 充当主回归方式。
