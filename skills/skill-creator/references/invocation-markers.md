# 调用标记规范（v0.2）

skill 正文中的工具调用用**固定标记**书写，使人与代码都能从正文抽取依赖。机器解析只看标记，不看散文。

## 目录

1. 四种载体
2. 书写规则
3. 抽取规则
4. 与正文原则的关系
5. 解析参考实现

## 1. 四种载体

| 载体 | 形态 | target | 例 |
|---|---|---|---|
| skill 调用 | `<use-skill>NAME</use-skill>` | skill 名（= 目录名） | `<use-skill>tdd</use-skill>` |
| MCP 调用 | `<mcp server="S" tool="T">参数</mcp>` | server 逻辑名 + 工具名 | `<mcp server="codegraph" tool="explore">AuthService</mcp>` |
| 宿主 tool | `<tool>NAME</tool>` | 宿主 tool 逻辑 id（小写） | `<tool>read</tool>` |
| shell 命令 | fenced block，首行 `# invocation` | binary 名 | 见下 |

shell 块形态：

````markdown
```bash
# invocation
git worktree add ".worktrees/{需求名}" "{需求名}"
```
````

可选预检加 `optional`：

````markdown
```bash
# invocation optional
command -v codegraph
```
````

## 2. 书写规则

1. 每种载体**仅此一种写法**：标签一律小写；不用自闭合；属性值双引号
2. **XML 区禁裸 `<`**：占位符在 XML 区写 `{需求名}`；bash 块内占位符照旧 `<需求名>`（代码块对 XML 透明）
3. target 用**逻辑名**：`read` 不写 `functions.Read`，`codegraph` 不写 `mcp__codegraph__explore`，`tdd` 不写路径
4. `<use-skill>` 不用 `<skill>`——后者与 harness 的 `<available_skills>` 声明块同形异义
5. `<tool>` 不用 `<function>`——对齐宿主配置键（`tools:`），「function」是 OpenAI 方言
6. 示例代码块**不写** `# invocation`；真命令必须带标记
7. 标记只钉依赖点：一行级、参数少的调用。多行命令序列进 `scripts/`，正文一行调用
8. 标记内不写解释性散文；说明文字放标记外的正文句子
9. **提及 ≠ 调用**：归属/路由类提及（「归 domains skill」）是散文，不打 `<use-skill>`；只有本 skill 执行中真实加载的 skill 才标
10. `<tool>` 只标非默认工具：read/write 类通用文件操作不标（否则每个 skill 全列一遍，纯噪声）；需预检或需权限的宿主工具才标
11. 同一步的多条命令可共用一个 invocation 块，逐命令的条件放行内注释（比每命令一块紧凑）
12. 示例/叙述节中的 skill 提及不打标记（场景故事非指令）
13. 迁移不新造字面命令：原文刻意留白给模型推导的命令保持散文，标记只转换已写出的字面命令
14. 列表项内可嵌 fence（缩进对齐列表项），解析器兼容
15. **skill 自带 scripts 的调用以 skill 目录为锚**：路径占位写 `<skill目录>`（= skill 加载时 harness 注入的 base directory），禁以会话 cwd 相对路径调用——模型cwd 是项目目录，相对路径会解析到项目下。例：`python3 "<skill目录>/scripts/foo.py"`
16. **scripts 自身必须 cwd 无关**：脚本内部路径一律从 `__file__` 推导（如本仓库 `skill-observe.py`、`parse-skill-invocations.py` 的 `SCRIPT_DIR`/`WORKSPACE` 模式），不读 cwd

## 3. 抽取规则

### XML 三类

```regex
<(use-skill|tool)\s*>\s*([^<]+?)\s*</\1>
<mcp\s+server="([^"]+)"\s+tool="([^"]+)"\s*>([^<]*)</mcp>
```

聚合：`<use-skill>` body → `skills[]`；`<tool>` body → `tools[]`；`<mcp>` 属性 → `mcp[] = {server, tool}`。

### bash 块

- 只取 info string 为 `bash`（或 `sh`）且**首行注释为 `# invocation`** 的块；其余代码块一律忽略
- 块内每条命令行（非空、非注释）取**首 token** 为 binary；过滤 shell 关键字与内建：`cd export if for while command sudo env time echo` 等
- 续行 `\` 并入上一条；管道右侧不视为新 binary
- `optional` 标注的计入 `shell-optional[]`

### 聚合输出

```json
{
  "skills": ["tdd"],
  "tools": ["read"],
  "mcp": [{"server": "codegraph", "tool": "explore"}],
  "shell": ["git"],
  "shell-optional": ["codegraph"]
}
```

## 4. 与正文原则的关系

- 标记是**元数据不是行为**：模型不靠标记也会调工具，标记纯为可解析服务。防膨胀：不为可解析把每句话包标签
- 与 `scripts/` 分工：审计四问第 4 档（必须字节级一致）仍归 scripts；invocation 块只承载一行级调用
- 正文仍写完成物与意图；标记替换的是「裸命令散文」，不替换工作流描述
- 抽取完整性靠作者自查与评审兜底（防静默缺项）；曾建 lint 工具，迁移期价值兑现后移除——持续校验待真实事故拉回

## 5. 解析参考实现

`scripts/parse-skill-invocations.py`（Python3 标准库）——只抽取，不校验：

```bash
# invocation
python3 scripts/parse-skill-invocations.py --all   # 解析 skills/*/SKILL.md → JSON
```

抽取边界：inline code 与非 invocation 代码块视为示例不参与；`&&`/`;` 分段各取首 binary，管道右侧不算；`sudo`/`env`/`command -v` 等引导词跳过找真 binary（`sudo -u ci npm` → `npm`）。不匹配严格形态的标记静默不抽取。
