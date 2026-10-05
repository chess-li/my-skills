# skills

SDD（规格驱动开发）Agent Plugin 及其治理仓库。`skills/` 下每个目录是插件内的一个 Agent Skill。

## 安装插件

```bash
bash scripts/install.sh
```

脚本从 `skills/` 生成一个 Agent Plugins 1.0.0 包，并通过三个 harness 的原生入口安装：

portable 包遵循 [Agent Plugins 1.0.0](https://agent-plugins.org/specification) 的 `plugin.json` 与 `skills/` 目录约定。

- **Codex**：写入本地 marketplace，然后调用 `codex plugin add`。
- **OpenCode**：保存插件源包，并把包内 `skills/` 目录加入全局 `skills` 配置。脚本会识别已有的 `opencode.jsonc`（含注释和尾逗号）或 `opencode.json`。OpenCode 的 `plugin` 数组只加载 JavaScript/TypeScript 代码插件，因此本项目使用它的 skills 配置方言。
- **Kimi Work**：生成 `kimi.plugin.json`，调用 Kimi 官方 `register-personal` 登记到个人市场。随后在 Kimi Work 的「个人」页签安装。

某个平台的客户端或原生脚本不存在时，结果会标记该平台为 skipped，并继续其他平台。

重复运行会更新同一个插件源和配置项。脚本不会删除旧版 `~/.agents/skills` 内容；`SKILLS_DEST` 与 `KIMI_SKILLS_DEST` 仅保留为弃用提示。

默认插件名为 `smooth`。插件名使用三端共用的 1-64 字符小写 kebab-case。版本使用 `x.y.z` 形式的 semver（可带 prerelease/build metadata），因为 Kimi Work 的原生校验要求该格式。仓库中故意省略描述的手动 skill 在生成包中会保留手动调用语义。启用 Codex 时，`AGENT_PLUGINS_HOME` 必须保持 `<root>/.agents/plugins` 结构；`CODEX_MARKETPLACE_FILE` 也必须是同一目录中的 `marketplace.json`，脚本据此把本地 marketplace 根目录交给 Codex CLI。

卸载当前插件：

```bash
bash scripts/uninstall.sh
```

卸载只处理 `smooth` 自己的源目录、OpenCode 路径、Codex 条目/cache 和 Kimi 个人市场登记；其他插件与历史 `~/.agents/skills` 内容保留。Codex CLI 不可用，或直接调用 Python 卸载时未提供 `KIMI_SHARE_DIR`，脚本会报告失败并保留源目录。默认 Shell 卸载会检查默认 Kimi share 目录；目录不存在且没有登记时仍可完成卸载。要清理旧版名称，显式运行 `PLUGIN_NAME=sdd-skills bash scripts/uninstall.sh`。Kimi 已在客户端个人页签安装的实例，仍需在 Kimi UI 中移除，因为官方 CLI 没有 unregister 命令。

常用环境变量：

```bash
PLUGIN_VERSION=1.0.0 bash scripts/install.sh
INSTALL_CODEX=0 bash scripts/install.sh
INSTALL_OPENCODE=0 bash scripts/install.sh
INSTALL_KIMI_WORK=0 bash scripts/install.sh
AGENT_PLUGINS_HOME="$HOME/.agents/plugins" bash scripts/install.sh
```

Kimi 桌面版不在默认路径时，可设置 `KIMI_PLUGIN_BUILDER`、`KIMI_DAIMON_BIN`、`KIMI_NODE_BIN` 和 `KIMI_SHARE_DIR`。

## 治理

- 创建、修改、审查任何 skill：先加载 `skills/skill-creator/`，纪律见 `AGENTS.md`
- 改动证据与观察名单：`skill-证据日志.md`
- 统一语言（领域术语）：`DOMAINS.md`
