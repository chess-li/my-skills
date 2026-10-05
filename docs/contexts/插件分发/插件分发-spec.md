# 插件分发

## 跨 harness 安装 Agent Plugin

### 动机

单独安装 skill 会让同一套能力在不同 harness 的目录、更新和卸载方式之间漂移。项目需要一个标准插件包，并为各 harness 提供原生安装入口。

### 用户故事

- 作为维护者，我想把 `skills/` 打包为一个 Agent Plugin，以便一套源内容可以分发到 OpenCode、Codex 和 Kimi Work。
- 作为用户，我想运行一次安装流程，以便各 harness 通过自己的插件入口发现和更新这套能力。
- 作为用户，我想卸载这一个插件，以便清理它自己的源包和三端登记，同时保留其他插件与旧版散装 skill。

### 验收标准

- 当构建插件时，应生成根部 `plugin.json`、`skills/<name>/SKILL.md`，并保留每个 skill 的脚本与参考文件；包内不得依赖根目录外的路径。
- 当构建插件时，插件名和每个 skill 名应使用三端共用的小写 kebab-case，skill frontmatter 的 `name` 应与目录名一致，版本应使用 Kimi Work 要求的 semver `x.y.z`（可带 prerelease/build metadata）。源 skill 缺少 `description` 时，生成包应补齐各平台需要的描述字段，并保留其手动调用语义。
- 当安装 Codex 方言时，应把插件登记到本地 marketplace，并由 Codex CLI 安装到其插件缓存；安装流程不得把 skill 单独复制到 `~/.agents/skills`。
- 当安装 OpenCode 方言时，应把插件放到插件源目录，并在 OpenCode 全局配置的 `skills` 数组中引用该插件的 `skills/` 目录；应识别官方支持的 JSONC 配置；重复安装不得添加重复配置。
- 当安装 Kimi Work 方言时，应生成 Kimi 原生 `kimi.plugin.json`，通过 Kimi 官方 CLI 登记到个人市场；没有 Kimi 客户端时应报告并继续完成其他方言。
- 当重复运行安装流程时，应覆盖本插件的源包、复用既有 marketplace 条目和 OpenCode 配置项，并保留其他插件与配置。
- 当任一平台安装失败时，应报告具体平台和原因；其他已成功的平台结果仍可使用。
- 当卸载插件时，应删除插件源目录、移除 OpenCode 的精确 skills 路径、按插件名和本插件的 local source path 移除 Codex marketplace 条目，并调用 Codex CLI 清理插件缓存；其他插件和配置必须保留。Codex CLI 不可用时应报告失败并保留源目录。
- 当卸载 Kimi Work 方言时，应按插件名和源路径精确移除个人市场登记；Kimi share 目录未知时应报告失败并保留源目录。Kimi 没有可用的官方卸载入口时，应报告未完成的客户端清理，不得删除其他插件条目。
- 当重复执行卸载流程时，应保持成功且不改变其他插件、配置或旧版 `~/.agents/skills` 内容。
- 默认插件名应为 `smooth`；历史 `sdd-skills` 安装必须通过显式指定旧名称单独清理，不自动删除。

## 变更历史

- 2026-10-05 新建：以 Agent Plugins 1.0.0 为 portable 包标准，并为 OpenCode、Codex、Kimi Work 定义平台方言。
