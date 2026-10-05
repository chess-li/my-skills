# 插件分发设计

## 跨 harness 安装 Agent Plugin

### 技术决策

- 使用 Agent Plugins 1.0.0 的根部 `plugin.json` 与固定 `skills/` 目录作为唯一 portable 包；构建时从仓库 `skills/` 复制文件，避免符号链接越过插件根目录。源 skill 缺少 `description` 时只在生成副本补平台元数据：OpenCode 使用 `metadata.opencode/autoinvoke: "false"`，Kimi Work 使用 `disableModelInvocation: true`，保持手动调用语义。
- 在同一包中保留 Codex 的 `.codex-plugin/plugin.json` 与 Kimi 的 `kimi.plugin.json` 适配清单；这些文件只表达平台元数据，不改变 portable manifest 和 skill 工作流正文。
- 把插件源包保存到用户级 `~/.agents/plugins/<name>`。Codex 的个人 marketplace 指向该目录，OpenCode 的 `skills` 配置指向该包的 `skills/` 子目录。这样更新只替换一个包，避免逐个 skill 同步。
- Kimi Work 只调用官方 `register-personal` 登记个人市场，不直接写入 Kimi 的 managed skills 目录；插件安装由 Kimi Work 的个人市场入口完成。
- 卸载使用同一个安装器的反向流程：先移除 OpenCode 精确路径和 Codex 原生安装，再按插件名与 local source path 收敛 marketplace，最后删除本插件源目录。Codex CLI 不存在时卸载失败并保留源目录，避免留下无法清理的 cache。Kimi 官方 CLI 没有 unregister 子命令，因此只在个人市场条目的源路径与本插件一致时删除该登记，并把已安装客户端状态报告给用户；未知 Kimi share 路径也会阻止源目录删除。
- 安装脚本使用 Python 处理 JSON 合并与文件复制，Shell 只负责平台探测、参数传递和结果汇总；一个平台失败不阻断其他平台。
- 插件名和 skill 名采用三端交集的小写 kebab-case，版本采用 Kimi Work 要求的 semver。OpenCode 配置读取 JSON 与 JSONC，并优先更新已经存在的 `opencode.jsonc`；Codex 根据 `<root>/.agents/plugins` 目录计算 marketplace 根，且只接受标准文件名 `marketplace.json`，避免自定义插件目录仍错误指向当前用户主目录。
- 默认插件 ID 为 `smooth`。旧 ID `sdd-skills` 不在普通安装中自动删除，避免误删用户自行维护的同名插件；迁移时显式运行 `PLUGIN_NAME=sdd-skills bash scripts/uninstall.sh`。

### 结构与契约

生成包包含：

```text
<plugin>/
├── plugin.json
├── .codex-plugin/plugin.json
├── kimi.plugin.json
└── skills/<skill-name>/SKILL.md
```

OpenCode 没有把 `plugin.json` 作为技能包安装入口。其方言使用官方 `skills` 配置数组引用 `<plugin>/skills`；代码插件数组不参与本能力。

## 变更历史

- 2026-10-05 新建：固化 portable 包与三种平台方言的边界。
