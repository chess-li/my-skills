---
status: open
category: enhancement
blockedBy: []
---

# WorkBuddy 插件安装与卸载

## 目标

为现有 Agent Plugin 安装流程增加 WorkBuddy 方言的安装与卸载，满足 `docs/contexts/插件分发/插件分发-spec.md` 中 WorkBuddy 方言的验收标准。

## 验收清单

- [ ] 当安装 WorkBuddy 方言时，应把本插件交给 WorkBuddy 应用内的 `codebuddy plugin` 命令完成用户级安装。未另行指定 CLI 时，该命令来自 WorkBuddy 应用包。完成后，指定用户主目录的 `.workbuddy` 中，本插件标识 `<本插件名>@<本插件市场名>` 应出现在已安装列表、处于启用状态，且该次版本的插件缓存包含本次插件源里的每个 `SKILL.md`。安装不得把 skill 单独复制到 `.workbuddy/skills`，不得写入该主目录的 `.codebuddy` 来代替，也不得写入其他主目录。
- [ ] 当重复安装 WorkBuddy 方言且版本字符串变化时，已安装列表应指向新版本，该版本缓存与本次插件源一致，并保留其他插件和其他市场。当版本字符串不变时，本插件应仍为已安装且启用；该方言不承诺改写这一版本已有缓存。
- [ ] 当 WorkBuddy CLI 不存在时，WorkBuddy 安装应标记为 skipped，不记为失败，且不创建或改写该主目录的 `.workbuddy` 插件登记。skipped 不使安装流程失败。其他平台继续。
- [ ] 当 WorkBuddy CLI 存在，但市场登记或插件安装没有使本插件处于已安装且启用状态时，应报告 WorkBuddy 失败和原因，且不自动重试。不得手写 `.workbuddy` 登记来代替该 CLI。其他已成功的平台结果仍可使用。CLI 进程退出码单独为 0 不足以把 WorkBuddy 记为成功；CLI 尚未返回时，不得把 WorkBuddy 记为成功。
- [ ] 当本次要使用的 WorkBuddy 市场名已有登记，且其目录源不是本插件的市场目录时，安装不得替换该登记，应报告失败。该登记、其他市场和其他插件必须保持原样。
- [ ] 当卸载 WorkBuddy 方言且 CLI 可用，并且本插件市场登记的目录源是本插件的市场目录时，卸载应移除本插件标识的已安装记录和启用记录，并移除该市场登记。其他插件、其他市场，以及目录源不是本插件市场目录的同名市场，必须保留。卸载不得删除 `.workbuddy/skills` 中的其他内容。
- [ ] 当本插件的 WorkBuddy 市场登记、已安装记录或启用记录都不存在时，该方言卸载成功。当 CLI 不存在，但上述任一登记存在时，应报告失败，不得手删这些登记，并保留源目录。
- [ ] 当同名 WorkBuddy 市场的目录源不是本插件的市场目录时，卸载不得按该市场名删除市场或插件，应报告失败并保留源目录。
- [ ] WorkBuddy 安装和卸载不承诺单独的等待时限、自动重试次数或并发上限。该平台只在对应 CLI 返回后才算完成。

## 显式出界

- 不把 `agy` 缺失时的 Gemini 安装改为 skipped。那是 `04_gemini安装在agy缺失时记为skipped_issue.md`。
- 不改 Gemini 卸载。
- 不手写 `.workbuddy` 插件登记，不调用 `PATH` 上的 `codebuddy`。
- 不自动点击 WorkBuddy 界面，不启用或禁用其他插件。

## 变更历史

- 2026-10-06 创建。用户要求增加 WorkBuddy 插件安装，并指出 `/Applications/WorkBuddy.app`。CLI 不存在时安装记为 skipped；卸载时有本插件登记而 CLI 不在则失败并保留源目录。
