# OpenCode 会话库结构（2026-11-24 核实）

读取条件：处理 OpenCode 会话库时读本文件。schema 随 OpenCode 版本漂移：提取脚本内置守卫（缺表缺列即报障并指回本文件；finish=tool-calls 的消息无部件即报障），报障时 `.schema` 实查后更新本文件。

## 库位置与打开方式

- 路径：`~/.local/share/opencode/opencode.db`(SQLite)。
- 只读打开：`sqlite3 "file:.../opencode.db?mode=ro"` 或脚本默认行为；该库是运行中库，写操作会污染取证对象。

## 表

- `session_v2`：会话。关键列：`id`、`directory`（工作目录，会话被 move 后更新为新目录，原目录见 location-switched 消息）、`parent_id`（子代理会话指父会话）、`title`、`model`、`time_created`/`time_updated`（epoch 毫秒）。异常收尾判定列：`idle_outcome`、`time_idle`、`time_suspended`、`resume_attempts`。
- `session_message`：消息头。关键列：`id`、`session_id`、`type`、`seq`（会话内序号）、`data`（JSON 全文）。
- `session_part`：assistant 消息部件（2026-11-24 起）。关键列：`message_id`（指 session_message.id）、`session_id`、`ordinal`（消息内部件序号）、`type`、`data`（JSON 全文）。主键 `(message_id, ordinal)`。

旧表 `session`/`message`/`part` 是迁移遗留，忽略它们。`session` 表 id 全集 ⊂ `session_v2`；`message`/`part` 有个位数迁移孤儿（2026-11-24 实测 message 表 6 条 session_id 不在 session_v2），不影响「忽略旧表」的结论。另有 `worktree`（项目登记的 worktree：project_id/directory/strategy/time_created）、`workspace`、`project_directory` 等表，worktree 取证时可用。

## 两代部件存储（2026-11-24 切换，同库并存）

- 切换前：assistant 部件内联在 `session_message.data.content[]`。
- 切换后：`data.content` 为空数组，部件在 `session_part`，按 message_id + ordinal 关联排序。
- 用户消息两代不变：`data.text` 是用户原话，永不进 session_part；空 text 剔掉。`data.files`、`data.agents` 是附件引用。
- assistant 消息头 `data` 还含：`model`、`finish`（tool-calls/stop/error/…）、`snapshot.files`（本消息触及的文件路径，多为相对路径，少量绝对路径并存）、`tokens`、`cost`。
- 部件 `data` 结构（两代同形）：按 `type` 分：
  - `text`：可见答复，`.text` 取文；
  - `reasoning`：推理部件，`.text` 取文——「判断事件是否发生」在这里取证；
  - `tool`：工具调用，`.name` 取工具名，`.state.input` 取入参（shell 是 `command`+`workdir`，edit/write 是 `filePath` 或 `path`——两字段并存须 coalesce，execute 是 `code`），`.state.content[]` 是工具结果。
- `type='idle'`：心跳消息，data 含 `outcome`（succeeded/failed/interrupted），与 `session_v2.idle_outcome` 同信息，无独立取证价值。
- `type='synthetic'`：系统续跑注入（如 "Continue if you have next steps…")，不是真人输入。
- 其余类型：`system`（系统注入）、`compaction`（压缩摘要，复盘长会话时它是上下文边界的标记）、`agent-switched`/`location-switched`/`model-switched`（生命周期事件，量小；location-switched 记会话 move 前后目录）。统计口径里这些都不是真人输入。

## 常用查询

提取用 `scripts/session_extract.py`（list/users/text/reasoning/tools/stats)。脚本覆盖不了的即席查询用 sqlite3，时间列是 epoch 毫秒：

```sql
datetime(time_created/1000,'unixepoch','localtime')
```

session_part 关联消息头排序：

```sql
SELECT p.* FROM session_part p
JOIN session_message m ON m.id = p.message_id
WHERE p.session_id = ? ORDER BY m.seq, p.ordinal;
```

## 已知坑

- `session_message.data.content` 为空数组 ≠ 无部件：2026-11-24 起部件在 session_part 表（见「两代部件存储」）。旧版提取器只读 content 会静默返回空——适配器守卫：finish=tool-calls 的消息必须取到工具部件，否则大声失败。
- finish=error/null/unknown 的消息可以合法地无部件（中断、错误），不是漂移。
- edit/write 工具入参路径字段 `filePath` 与 `path` 并存（同库两种都出现），统计编辑足迹时必须 coalesce 两字段，否则漏计。
- `users` 子命令只剔空消息；用户消息里仍可能混入 system-reminder 等注入形态，还原真人输入时须人工剔除（类型层的 system/synthetic 见上节）。
- 子代理会话量大且是主会话的执行细节；`list`/`stats` 默认含子代理会话，宏观统计加 `--main-only`（`parent_id IS NULL`）分出主会话，再决定是否下钻。归属主会话的编辑足迹用递归 CTE 沿 parent_id 汇总。
- 会话库只记本会话 harness；Codex 的 rollout jsonl 等其他 harness 的会话存储各找各的。
