---
status: doing
category: enhancement
blockedBy: []
---

# 安装插件而非散装 skill

## 目标

把仓库的 skill 管理改为 Agent Plugin 分发，满足 `docs/contexts/插件分发/插件分发-spec.md` 的验收标准。

基线分支：main

## 验收清单

- [x] 构建 portable `plugin.json` 与 `skills/` 包，并通过包结构校验 —— 已验证：`python3 -m unittest discover -s scripts/tests -p 'test_*.py'`，22 tests OK；Kimi 官方 `validate_plugin.py` 0 error/0 warning；25 个 skill 均含匹配目录名的 frontmatter `name` 和生成后的 `description`，手动 skill 同时带 OpenCode/Kimi 禁自动调用字段（2026-10-05）
- [x] Codex 使用本地 marketplace 和 CLI 安装插件，不再复制散装 skill —— 已验证：临时 `HOME`/`CODEX_HOME` 运行 `bash scripts/install.sh`，`codex plugin list --json` 显示 `smooth@workspace-skills` 已安装，缓存路径含 `plugin.json`；自定义外部 `<root>/.agents/plugins` 也能正确登记；未创建 `~/.agents/skills`（2026-10-05）
- [x] OpenCode 通过全局 `skills` 配置引用插件包 —— 已验证：临时 `opencode.jsonc` 含注释和尾逗号，运行安装脚本后 `skills` 仅含插件包 `skills/` 路径；重复运行不新增 `opencode.json`（2026-10-05）
- [x] Kimi Work 生成并校验 `kimi.plugin.json`，有客户端时走官方登记 —— 已验证：Kimi `validate_plugin.py` 0 error/0 warning；官方 `register_personal.py` 在不存在的临时 share 登记成功，返回个人市场条目（2026-10-05）
- [x] 重复安装幂等且不改其他插件或配置 —— 已验证：同一临时 HOME 连续运行两次，marketplace 仍 1 个插件、OpenCode `skills` 仍 1 个路径，Codex 版本缓存可读（2026-10-05）
- [x] 单个平台失败时继续其他平台并报告原因 —— 已验证：测试用 Kimi 登记脚本返回非零后，安装返回 `failures: ["kimi-work"]`，插件源和 OpenCode 配置仍完成（2026-10-05）
- [x] 卸载删除本插件源目录、OpenCode 精确路径、Codex 原生安装与 marketplace 条目，并保留其他插件 —— 已验证：三平台临时环境完整安装后运行 `bash scripts/uninstall.sh`，源目录、marketplace 条目、Codex cache 和 OpenCode 路径均清理，其他条目保留；Codex CLI 缺失时测试确认保留源目录和 cache（2026-10-05）
- [x] 卸载 Kimi 个人市场登记时校验插件名和源路径；无官方 unregister 时报告客户端清理边界 —— 已验证：真实 Kimi personal entry 的 `id`/`sourcePath` 可删除；已安装状态返回 UI 清理提示，不删除其他条目（2026-10-05）
- [x] 重复卸载幂等，且不触碰旧 `~/.agents/skills` —— 已验证：连续两次卸载均返回 `failures=[]`；旧目录保持原样；Kimi share 未提供时测试确认保留源目录（2026-10-05）
- [x] 默认插件名改为 `smooth`，旧 `sdd-skills` 只通过显式名称清理 —— 已验证：默认安装目录、portable manifest、Codex/Kimi 清单和 CLI 选择器均为 `smooth`；`PLUGIN_NAME=sdd-skills` 可单独卸载旧目录（2026-10-05）

## 显式出界

- 不删除用户以前由旧脚本安装的 `~/.agents/skills` 内容。
- 不实现 OpenCode 的 JavaScript/TypeScript 代码插件；本任务只分发 skills。
- 不自动点击 Kimi Work UI 的“个人”市场安装按钮。

## 足迹

- 仓库：`/Users/chess/workspace/skills`
- 计划触碰：`scripts/install.sh`、`scripts/uninstall.sh`、`scripts/build_plugin.py`、`scripts/plugin_installer.py`、`scripts/tests/`、`README.md`、`DOMAINS.md`、`docs/contexts/插件分发/`、`docs/issues/插件分发/`

## 当前位置

实现与验证已完成：已加入卸载流程，默认插件名已改为 `smooth`；等待任务保留/合入选择。

## 变更历史

- 2026-10-05 创建并开始执行；用户要求改为插件分发，统一标准为 agent-plugins.org。
- 2026-10-05 根据用户要求补充卸载流程，并将默认插件名改为 `smooth`；增加三平台卸载、Kimi 源路径校验、重复卸载和旧名称显式清理验证。

## 范围外问题

- 旧 `scripts/install.sh` 会把 skill 复制到 `~/.agents/skills`；本任务替换其行为，但不清理历史目录。

## 评审自检

- 独立评审发现并已处理：OpenCode JSONC 读取与默认文件选择、Kimi kebab-case 名称交集、skill 目录/frontmatter 校验、Kimi 手动调用字段、Codex marketplace 根计算与标准文件名、重复条目收敛、Kimi 自定义 share 路径透传、证据日志换行和 Python 测试产物忽略。
- 第二轮独立评审发现并已处理：Codex CLI 缺失时保留源目录与 cache、Codex marketplace 按名称和 local source path 精确匹配、Kimi share 未提供时保留源目录；最终复审无未处理发现。
- 回归：`python3 -m unittest discover -s scripts/tests -p 'test_*.py'`（22 tests OK）；`bash -n scripts/install.sh scripts/uninstall.sh`；`python3 -m py_compile scripts/build_plugin.py scripts/plugin_installer.py`；`git diff --check`。

## 三面摘要

- 完整性：通过；spec 十一条验收标准均有实测或自动化证据，显式出界项仍未执行。
- 正确性：通过；官方 Kimi validator/register 与 Codex CLI 临时环境通过，OpenCode JSONC 和失败隔离有回归测试。
- 一致性：通过；portable manifest、Codex/OpenCode/Kimi 方言、README、spec/design 和安装脚本使用同一插件源模型。
