---
status: doing
category: enhancement
blockedBy: []
---

# Gemini 插件安装与卸载

## 目标

为现有 Agent Plugin 安装流程增加 Gemini 方言的安装与卸载，满足 `docs/contexts/插件分发/插件分发-spec.md` 中 Gemini 方言的验收标准。

基线分支：main
起点 commit：98c16f7
提交区间：98c16f7..405e65d

## 验收清单

- [x] 当安装 Gemini 方言时，应把插件源目录交给 Antigravity CLI 的 `agy plugin install`。完成后，该用户主目录下的 `.gemini/config/plugins/<本插件名>` 应包含该插件，且 `.gemini/config/import_manifest.json` 中该插件名只有一条导入记录。安装不得调用 `gemini extensions`，不得生成 `gemini-extension.json`，也不得把 skill 单独复制到 `.gemini/config/skills`。 —— 已验证：`test_cli_installs_gemini_copy_through_agy_in_the_specified_home`，包装 `agy` 记录 `HOME` 与 `plugin install <源目录>` 后转交真实 CLI，副本与一条导入记录成立（2026-10-05）
- [x] 当重复安装 Gemini 方言时，应覆盖本插件的 Gemini 副本，保持一条导入记录，并保留其他名称的插件。 —— 已验证：`test_repeat_gemini_install_overwrites_copy_and_keeps_other_plugin`，第二次安装去掉 `marker.txt`，导入记录为 `smooth`、`other`（2026-10-05）
- [x] 当 `agy` 不存在，或 `agy plugin install` 返回失败时，应报告 Gemini 失败和原因，且不自动重试。其他已成功的平台结果仍可使用。安装流程不得改写 `.gemini` 来代替该 CLI。 —— 已验证：`test_missing_agy_reports_gemini_failure_without_writing_config` 的 `failures` 为 `["gemini"]` 且 OpenCode 配置仍写入；`test_failing_agy_install_is_not_retried` 的失败调用计数为 1，未创建 `.gemini`（2026-10-05）
- [x] 安装和卸载使用一个用户主目录。未另行指定时，该目录是当前用户主目录。Gemini 副本和导入记录只应出现在该主目录的 `.gemini` 下，不得写入其他主目录。 —— 已验证：同上安装测试把 `HOME` 设为临时主目录，真实用户 `~/.gemini/config/plugins` 的 mtime 不变（2026-10-05）
- [x] 当 `agy` 可用，且本插件的 Gemini 副本不存在或副本中 `plugin.json` 的 `name` 与本插件名一致时，卸载应按本插件名调用 `agy plugin uninstall`。该调用应移除本插件副本和该名称的导入记录。副本本来不存在时，该方言卸载仍成功。其他名称的插件和导入记录必须保留。 —— 已验证：`test_cli_uninstalls_gemini_copy_and_keeps_another_plugin`，日志为 `plugin uninstall smooth`，`other` 保留，源目录删除（2026-10-05）
- [x] 当 `.gemini/config/plugins/<本插件名>` 存在，但其 `plugin.json` 缺失、不是合法 JSON，或 `name` 不是本插件名时，卸载不得删除该目录，应报告失败并保留源目录。 —— 已验证：`test_gemini_uninstall_keeps_same_name_directory_with_a_different_manifest_name`、`test_gemini_uninstall_keeps_directory_without_a_manifest`、`test_gemini_uninstall_keeps_directory_with_invalid_manifest_json`，三例均 `failures=["gemini"]` 且未调用 `agy`（2026-10-05）
- [x] 当 `agy` 不存在，且本插件的 Gemini 副本与导入记录都不存在时，Gemini 卸载应成功。当 `agy` 不存在，但副本或导入记录存在时，应报告失败，不得手删副本或导入记录，并保留源目录。 —— 已验证：`test_gemini_uninstall_without_agy_succeeds_when_nothing_is_installed` 返回码 0；`test_gemini_uninstall_without_agy_keeps_existing_copy_and_source` 与 `test_gemini_uninstall_without_agy_keeps_import_record` 保留副本或导入记录和源目录（2026-10-05）
- [x] Gemini 安装和卸载不承诺单独的等待时限、自动重试次数或并发上限。该平台只在对应 CLI 返回后才算完成；CLI 尚未返回时，不得把 Gemini 记为成功。 —— 已验证：`test_gemini_install_waits_until_agy_returns` 等待至少 0.4 秒后才成功；失败调用只发生一次（2026-10-05）

## 显式出界

- 不实现 `gemini extensions` 或 `gemini-extension.json`。
- 不改主目录里尚未提交的 README 场景目录说明和 skill-creator 路径。
- 不自动启用或禁用 Gemini 插件；只做安装与卸载。

## 足迹

- 仓库：`/Users/chess/workspace/skills`
- 计划触碰：`scripts/plugin_installer.py`、`scripts/install.sh`、`scripts/tests/test_plugin_installer.py`、`README.md` 的安装说明、本 issue

## 当前位置

验收清单已有测试证据。等待提交实现，并做归档前评审。

## 三面摘要

- 完整性：通过；Gemini 方言八条验收标准均有对应测试。显式出界项未执行。
- 正确性：通过；`python3 -m unittest discover -s scripts/tests -p 'test_*.py'`，38 tests OK（2026-10-05）。
- 一致性：通过；安装与卸载都走 `agy plugin`，不生成 `gemini-extension.json`，不手写 `.gemini`。

## 变更历史

- 2026-10-05 创建并开始执行。用户裁定 Gemini 入口为 Antigravity CLI 的 `agy plugin`，并要求直接在主目录改代码。
- 2026-10-05 验收清单八条均有测试证据；全量 `scripts/tests` 38 tests OK。
