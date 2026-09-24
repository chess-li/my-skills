# skills

SDD（规格驱动开发）agent skill 集合及其治理仓库。`skills/` 下每个目录是一个对外分发的 skill，共 20 个。

## 安装

```bash
bash scripts/install.sh
```

同步 `skills/*` 到 `~/.agents/skills/`（目标可用 `SKILLS_DEST` 覆盖）；检测到 kimi-desktop 共享目录时一并软链（可用 `KIMI_SKILLS_DEST` 覆盖）。

## 治理

- 创建、修改、审查任何 skill：先加载 `skills/skill-creator/`，纪律见 `AGENTS.md`
- 改动证据与观察名单：`skill-证据日志.md`
- 统一语言（领域术语）：`DOMAINS.md`
- skill 依赖抽取：`python3 scripts/parse-skill-invocations.py --all`
