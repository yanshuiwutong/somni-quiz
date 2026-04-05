# DOCX Regression Coverage Matrix

This matrix tracks which scenarios from the two acceptance documents are covered by local blackbox goldens.

| Source | Section / Issue | Example Input | Expected Behavior | Coverage Status | Golden Cases |
| --- | --- | --- | --- | --- | --- |
| 测试结果 .docx | 正常对话 | 截图型流程 | 正常顺序推进问卷 | visual_only | 截图为主，待后续补更完整长流程 case |
| 测试结果 .docx | 不完整信息处理 | `11点睡` -> `7点起` | partial 后补全 question-02 | covered | `runtime_partial_followup`, `streamlit_docx_partial_followup`, `grpc_docx_partial_followup` |
| 测试结果 .docx | 中途修改 | `我改成25-34岁` | 修改已答题 | covered | `runtime_docx_modify_answered` |
| 测试结果 .docx | 查看记录 | `查看记录` | 返回当前记录摘要，不丢答案 | covered | `grpc_docx_view_all`, `runtime_docx_view_all`, `streamlit_docx_view_all` |
| 测试结果 .docx | 闲聊 / 身份询问拉回 | `你是谁` | 短句接住后回到当前睡眠题 | covered | `grpc_non_content_identity_pullback`, `streamlit_non_content_identity_pullback` |
| 测试结果 .docx | 查看上一题记录 | `查看上一题记录` | 返回上一题记录且不切走当前题 | covered | `grpc_non_content_view_previous`, `streamlit_non_content_view_previous` |
| 测试结果 .docx | 一次回答多项 | `我22岁，每天11点睡觉，7点起床` | 只命中年龄 + 常规作息 | covered | `runtime_docx_multi_answer`, `grpc_docx_multi_answer`, `streamlit_docx_multi_answer` |
| 测试结果 .docx | 无llm硬匹配兜底 | 无网/无模型规则兜底 | 规则回退仍可完成主要映射 | covered | 现有 regression 默认无 provider，`runtime_docx_free_sleep_23`, `runtime_docx_free_wake_around_7`, `runtime_docx_wake_back_ten_minutes` |
| 测试结果 .docx | 补测 1 | `那7左右` | 命中 `question-04` / `B` | covered | `runtime_docx_free_wake_around_7` |
| 测试结果 .docx | 补测 1 | `23点` | 命中 `question-03` / `B` | covered | `runtime_docx_free_sleep_23` |
| 测试结果 .docx | 补测 2 | 已答题再次命中 | 默认识别为修改 | covered | `runtime_docx_modify_answered`, `runtime_docx_modify_free_wake_answered` |
| 测试结果 .docx | 补测 3 | `我22岁，每天11点睡觉，7点起床` | 不应误命中自由作息题 | covered | `runtime_docx_multi_answer`, `grpc_docx_multi_answer`, `streamlit_docx_multi_answer` |
| 测试结果 .docx | 补测 4 | `十来分钟` | 命中 `question-08` / `A` | covered | `runtime_docx_wake_back_ten_minutes` |
| 测试报告 .docx | 问题 1 | `那7左右` | 修正为 `question-04` / `B` | covered | `runtime_docx_free_wake_around_7` |
| 测试报告 .docx | 问题 1 | `23点` | 修正为 `question-03` / `B` | covered | `runtime_docx_free_sleep_23` |
| 测试报告 .docx | 问题 2 | `自由安排的话，我会七点起床` | 修改已答 `question-04` | covered | `runtime_docx_modify_free_wake_answered`, `grpc_docx_modify_free_wake_answered`, `streamlit_docx_modify_free_wake_answered` |
| 测试报告 .docx | 问题 2 | `改成十点` / `更改为十点` | 自然语言修改最近相关时间题 | covered | `runtime_docx_modify_to_ten_oclock`, `grpc_docx_modify_to_ten_oclock`, `streamlit_docx_modify_to_ten_oclock` |
| 测试报告 .docx | 问题 3 | `我22岁，每天11点睡觉，7点起床` | 不应同时命中自由入睡 / 起床 | covered | `runtime_docx_multi_answer`, `grpc_docx_multi_answer`, `streamlit_docx_multi_answer` |
| 测试报告 .docx | 问题 4 | `十来分钟` | 修正为 `question-08` / `A` | covered | `runtime_docx_wake_back_ten_minutes` |

## Online Smoke Additions

- `test_real_provider_non_content_identity_pullback_business9`
- `test_real_provider_non_content_view_previous_business9`

这些在线 smoke 只校验状态与非空回复，不绑定真实模型的自由表达措辞。
