---
name: local-env
description: 维护项目本地运行目录 `.local-env`：发现入口、引导创建、执行 start 立通道。用于：建立或补齐 `.local-env`；启动本地程序；debug 立通道时路由过来。不用于 bug 诊断与修复（debug 的事）；不用于测试构建信道（tdd 的事）；不用于项目文档初始化（bootstrap 的事）。
---

# 本地运行目录

## 意图锚点（每次使用前必读）

本 skill 守护一条主线：**跨机器只钉 `.local-env` 契约；缺则引导创建，有则执行 start 立通道。**

护栏：
- 契约：项目根 `.local-env/start`（可执行）与 `.local-env/url`（非空，探活地址）；目录本身或其中文件可以是软链
- `.local-env/` 不进版本库；本机用软链把该路径指到本机环境
- 本轮用户给出的地址优先于 url 文件
- 不诊断、不修 bug

## 核心工作流

### 1. 探入口

查项目根 `.local-env/start` 与 `.local-env/url`（跟随软链）。可用 = start 可执行且 url 非空。产物：可用，或缺哪些。

### 2. 缺则引导创建

入口不可用 → 引导创建，不停下空要文件。一次一问：

1. 本机环境目录在哪？推荐：没有现成目录 → 在项目根建 `.local-env`；已有 → `ln -s` 到项目根 `.local-env`
2. start：有现成启动脚本 → 链为 `.local-env/start`；否则从 AGENTS.md/README 推断启动命令写成 start，请用户认
3. url：本轮已给地址 → 直接写入不问；否则问探活地址

`.gitignore` 无 `.local-env` → 补上。产物：可用的 start 与 url。

```bash
# invocation
ln -s {本机环境目录} .local-env
```

### 3. 立通道

```bash
# invocation
.local-env/start
```

工作目录 = 项目根。按 url 探活（本轮用户给出的地址优先）。产物：该地址可连。start 失败 → 把原始输出给用户，不用运行时诊断代替立通道。

### 4. 返回

调用方是 debug → 交回「通道已立」与实际 url。无调用方 → 告知已立。

## 授权分档

- 直接执行：探入口、读文件、探活、执行 start
- 执行后告知：补 `.gitignore`、按引导结果写 start/url、`ln -s` / 建目录
- 必须先确认：删除已有 `.local-env`
