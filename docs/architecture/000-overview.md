# Overview

> 本文件是 `somni-graph-quiz` 的总览入口。后续阅读顺序、文档边界、目录结构和核心设计原则都以本文件为索引。

## Goal

为新项目提供统一总览，回答四个问题：

1. 这个新项目要解决什么问题
2. 核心架构由哪些部分组成
3. 关键文档分别负责什么
4. 后续实现应如何从文档落到代码

## Project Positioning

`somni-graph-quiz` 是一个独立于当前老项目的新项目目录。

它的目标不是在旧代码上继续堆补丁，而是基于已经验证过的业务需求，重新组织为：

- 清晰的三层节点架构
- 统一的状态模型
- LLM 主判定、规则仅在无网时兜底
- gRPC 与 Streamlit 共用一套 graph runtime
- 对外接口兼容，但内部实现边界更清楚

## Core Design Principles

- 主分支互斥：`non_content | content`
- `content` 域内允许多题并行命中
- 已答题再次命中自动视为修改
- partial 独立存储，不混入完整答案
- 只有一个最终响应节点对用户说话
- prompt、状态、节点、测试四部分分别建文档，不混写
- 当前项目仅作为业务参考，新项目代码与目录独立演进

## Architecture Snapshot

整体结构分四块：

1. 状态层
   - 定义 `GraphState`、`SessionMemory`、`TurnContext`
2. 节点层
   - 定义单轮执行链与各节点职责
3. prompt 层
   - 定义 LLM 节点输入、输出、共享术语和降级边界
4. 测试层
   - 定义契约、节点、运行时和适配层回归

### Single-Turn Flow

```text
TurnInput
  -> TurnClassifyNode
  -> NonContentBranch | ContentBranch
  -> TurnFinalizeNode
  -> ResponseComposerNode
  -> TurnResult
```

## Document Reading Order

建议按以下顺序阅读：

1. [010-state-model.md](./010-state-model.md)
   - 看状态字段、只读边界、partial 与 answered 的存储位置
2. [020-node-graph.md](./020-node-graph.md)
   - 看节点顺序、主分支、ContentApply 与 TurnFinalize 职责
3. [030-prompt-layout.md](./030-prompt-layout.md)
   - 看哪些节点需要 prompt、输入摘要如何组织、fallback 如何约束
4. [040-test-layout.md](./040-test-layout.md)
   - 看测试分层、结构化回归样例和接口兼容验证方式

## Directory Snapshot

```text
somni-graph-quiz/
  docs/
    architecture/
    decisions/
    plans/
  prompts/
    layer1/
    layer2/
    layer3/
    shared/
  src/
    somni_graph_quiz/
  tests/
    unit/
    integration/
    regression/
```

## Runtime Boundary

### Static Layer

- `question_catalog`
- prompt files
- architecture docs

这些是静态资产，不随单轮输入变化。

### Runtime Layer

- `session_memory`
- `runtime`
- `turn`
- `artifacts`

这些是会话运行态，由节点输出 patch 后统一合并。

## LLM Usage Policy

- LLM 是主判断路径，不是装饰层。
- 规则不是常态分流，只是无网和不可用时的故障兜底。
- `non_content` 以规则优先，不额外建立 prompt 家族。
- `content` 域内的候选提取、动作识别、归属裁决、文本选项映射由 prompt 文档约束。

## Compatibility Goal

新项目内部可以大改，但以下外部能力必须保持：

- gRPC 接口逻辑不变
- gRPC 输入输出格式不变
- Streamlit 继续保留
- 老项目能作为业务与样例参考源

## What Is Already Defined

当前已完成定义：

- 状态模型
- 节点图
- prompt 布局
- prompt 文件骨架与共享契约
- 测试布局
- 新项目目录骨架

## What Comes Next

下一阶段应从文档进入实现骨架，优先顺序建议为：

1. 建立 `src/` 下的状态模型与节点接口骨架
2. 建立 fake LLM 与 runtime 测试基建
3. 优先打通最小单轮链路
4. 再接入 grpc / streamlit adapter
5. 用结构化 regression cases 覆盖关键业务场景

## Non-Goals

- 不在本阶段改动老项目主链路
- 不在没有状态和节点契约前直接写业务实现
- 不依赖真实公网或真实在线模型作为默认验证路径
