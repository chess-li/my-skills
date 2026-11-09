# Codex rollout 结构（2026-10-20 核实）

读取条件：处理 Codex 历史会话时读本文件。本文件结论在本机 179 个真实 rollout 文件上核实；Codex 升级改格式时以真实文件实查为准。

## 存储位置

- 活跃：`~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-<时间戳>-<session_uuid>.jsonl[.zst]`
- 归档：`~/.codex/archived_sessions/`（平铺）
- `.zst` 是 zstd 压缩；Python 3.14+ 用 `compression.zstd` 直读。
- 同一会话每次 resume 产生一份新 rollout（归档文件名可带 `_<resume_uuid>` 后缀）：列表按 session_uuid 去重，消息提取合并同会话全部文件、按文件名时间序。

## 行结构

每行一个 JSON：`{type, payload, ...}`。

- `type='session_meta'`：payload 含 `session_id`、`cwd`、`originator`、`cli_version`——列表的目录与来源取自这里。
- `type='response_item'`：对话与工具事件，`payload.type` 区分：
  - `message`：`role` = user/assistant；`content[]` 元素 `input_text`（用户）/ `output_text`（助手），取 `.text`。
  - `reasoning`：推理部件——`summary[]` 可能有可读文本，否则 `encrypted_content` 加密不可读、只能计数。「判断事件是否发生」取证在 Codex 侧不一定可用。
  - `function_call` / `custom_tool_call`：工具调用，取 `.name`。
- 其余 `type`（`event_msg`/`turn_context`/`world_state`/`token_usage_record` 等）：生命周期与统计事件，量大，取证一般不用。

## 已知坑

- reasoning 加密：以 summary 有无文本为准；提取结果为 None 即不可读——报告条数，不编造内容。
- `role=user` 消息大量是环境与指令注入（`environment_context`、AGENTS.md 注入、`external_codex_apps` 等）；还原真人输入须人工剔除，脚本只剔空消息。
- 列表的 `created` = 首份 rollout 文件名日期；resume 会话在 `--since` 过滤下按首份文件日期的口径计数。
- jsonl 无 schema 可守：解析失败的行跳过并计数，尾部报告；payload 非 dict 的行同样跳过；候选文件名不匹配命名方案时计数报障——2026-09 前存在 `ses_*` 旧命名的孤儿 rollout，不匹配计数基线可能非零，关注计数**变化**，不关注绝对值。
- 会话无 title 字段（列表标题列展示 `originator`）；`session_meta` 另有 `model_provider` 等字段，是否稳定可用未核实。
