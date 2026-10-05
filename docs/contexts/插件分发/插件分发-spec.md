# 插件分发

## 跨 harness 安装 Agent Plugin

### 动机

单独安装 skill 会让同一套能力在不同 harness 的目录、更新和卸载方式之间漂移。项目需要一个标准插件包，并为各 harness 提供原生安装入口。

### 用户故事

- 作为维护者，我想把 `skills/` 打包为一个 Agent Plugin，以便一套源内容可以分发到 OpenCode、Codex、Kimi Work 和 Gemini。
- 作为用户，我想运行一次安装流程，以便各 harness 通过自己的插件入口发现和更新这套能力。
- 作为用户，我想卸载这一个插件，以便清理它自己的源包和各 harness 登记，同时保留其他插件与旧版散装 skill。

### 验收标准

- 当构建插件时，应生成根部 `plugin.json`、`skills/<name>/SKILL.md`，并保留每个 skill 的脚本与参考文件；包内不得依赖根目录外的路径。
- 当构建插件时，插件名和每个 skill 名应使用各 harness 共用的小写 kebab-case，skill frontmatter 的 `name` 应与目录名一致，版本应使用 Kimi Work 要求的 semver `x.y.z`（可带 prerelease/build metadata）。源 skill 缺少 `description` 时，生成包应补齐各平台需要的描述字段，并保留其手动调用语义。
- 当安装 Codex 方言时，应把插件登记到本地 marketplace，并由 Codex CLI 安装到其插件缓存；安装流程不得把 skill 单独复制到 `~/.agents/skills`。
- 当安装 OpenCode 方言时，应把插件放到插件源目录，并在 OpenCode 全局配置的 `skills` 数组中引用该插件的 `skills/` 目录；应识别官方支持的 JSONC 配置；重复安装不得添加重复配置。
- 当安装 Kimi Work 方言时，应生成 Kimi 原生 `kimi.plugin.json`，通过 Kimi 官方 CLI 登记到个人市场；没有 Kimi 客户端时应报告并继续完成其他方言。
- 当重复运行安装流程时，应覆盖本插件的源包、复用既有 marketplace 条目和 OpenCode 配置项，并保留其他插件与配置。
- 当任一平台安装失败时，应报告具体平台和原因；其他已成功的平台结果仍可使用。
- 当卸载插件时，应删除插件源目录、移除 OpenCode 的精确 skills 路径、按插件名和本插件的 local source path 移除 Codex marketplace 条目，并调用 Codex CLI 清理插件缓存；其他插件和配置必须保留。Codex CLI 不可用时应报告失败并保留源目录。
- 当卸载 Kimi Work 方言时，应按插件名和源路径精确移除个人市场登记；Kimi share 目录未知时应报告失败并保留源目录。Kimi 没有可用的官方卸载入口时，应报告未完成的客户端清理，不得删除其他插件条目。
- 当重复执行卸载流程时，应保持成功且不改变其他插件、配置或旧版 `~/.agents/skills` 内容。
- 默认插件名应为 `smooth`；历史 `sdd-skills` 安装必须通过显式指定旧名称单独清理，不自动删除。
- 当安装 Gemini 方言时，应把已生成的插件目录交给 Antigravity CLI 的 `agy plugin install`。完成后，该用户主目录下的 `.gemini/config/plugins/<本插件名>` 应包含该插件，且 `.gemini/config/import_manifest.json` 中该插件名只有一条导入记录。安装不得调用 `gemini extensions`，不得生成 `gemini-extension.json`，也不得把 skill 单独复制到 `.gemini/config/skills`。
- 当重复安装 Gemini 方言时，应覆盖本插件的 Gemini 副本，保持一条导入记录，并保留其他名称的插件。
- 当 `agy` 不存在，或 `agy plugin install` 返回失败时，应报告 Gemini 失败和原因，且不自动重试。其他已成功的平台结果仍可使用。安装流程不得改写 `.gemini` 来代替该 CLI。
- 安装和卸载使用一个用户主目录。未另行指定时，该目录是当前用户主目录。Gemini 副本和导入记录只应出现在该主目录的 `.gemini` 下，不得写入其他主目录。
- 当 `agy` 可用，且本插件的 Gemini 副本不存在或副本中 `plugin.json` 的 `name` 与本插件名一致时，卸载应按本插件名调用 `agy plugin uninstall`。该调用应移除本插件副本和该名称的导入记录。副本本来不存在时，该方言卸载仍成功。其他名称的插件和导入记录必须保留。
- 当 `.gemini/config/plugins/<本插件名>` 存在，但其 `plugin.json` 缺失、不是合法 JSON，或 `name` 不是本插件名时，卸载不得删除该目录，应报告失败并保留源目录。
- 当 `agy` 不存在，且本插件的 Gemini 副本与导入记录都不存在时，Gemini 卸载应成功。当 `agy` 不存在，但副本或导入记录存在时，应报告失败，不得手删副本或导入记录，并保留源目录。
- Gemini 安装和卸载不承诺单独的等待时限、自动重试次数或并发上限。该平台只在对应 CLI 返回后才算完成；CLI 尚未返回时，不得把 Gemini 记为成功。

## 变更历史

- 2026-10-05 新建：以 Agent Plugins 1.0.0 为 portable 包标准，并为 OpenCode、Codex、Kimi Work 定义平台方言。
- 2026-10-05 变更：增加 Gemini 方言的安装与卸载。入口是 Antigravity CLI 的 `agy plugin`，不使用 `gemini extensions`。
