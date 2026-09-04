# code-review 冒烟集

真实语料欠账：工作流用例为按 testing-guide §9 构造的扰动变体。2026-08-05 智能体节点真实编码会话到场：R01/R02 场景获真实使用佐证（新鲜上下文评审、裁决门禁、scoped 重审均实际执行，见证据日志同日补注），正式回归未跑。

跑法：改动后必跑受影响子集。工作流用例需干净会话 + 有真实变更的练手项目（加载 code-review skill，按用例输入执行，逐条对照硬性断言）；触发测试集单条几秒钟（`opencode run --dir <空目录> --title trigger-<ID> "<输入>"`，再查会话 DB 的 skill 加载记录）。

## 工作流用例

```
用例 ID: R01
用户处境: 变更写完，提交前想要独立把关
真实输入: 改动写完了，提交前帮我看看有没有问题
验收标准:
  - 硬性: 评审在新鲜上下文中进行（评审者拿不到实现过程的会话历史），实现者自审不充当评审
  - 硬性: 产出分级发现（Critical/Important/Minor 带 file:line）与明确裁决（可合入 / 修复后重审）
  - 软性: 发现指向真实问题，无"看起来不错"式空评
来源: 扰动变体
```

```
用例 ID: R02
用户处境: implement 流程内，验证全部通过后进入归档
真实输入: （任务文件验收清单全绿，按 implement 第 6 步走到评审环节）
验收标准:
  - 硬性: implement 主动派发 code-review，裁决可合入才归档；有 Critical/Important → 修复后回验证，不跳过
  - 硬性: 评审范围 = 任务分支相对基线分支的变更
来源: implement 消费端联动
```

```
用例 ID: R03
用户处境: 评审一个新增与既有同类平行代码的变更
真实输入: （变更新增一个 *FormData 类与若干异常抛出点，请评审）
验收标准:
  - 硬性: 评审者实际读同类文件对比（结构/命名/错误处理），不一致处列为发现并附 file:line
  - 硬性: 惯例一致性结论有同类文件依据，不采实现者自述
来源: 2026-08-06 返工事件（两轮评审可合入后，用户仍发现 FormData 无层级、魔法值异常两处同类惯例不一致）
```

```
用例 ID: R04
用户处境: 评审含方法体未引用参数、测试专用构造器的变更
真实输入: review ey-timp-lab-ai-infra（ses_f97eac052ffe 现场：ShellCommandRules.record 死参数、ScriptDependencyReport 双参构造器仅测试消费）
验收标准:
  - 硬性: 该死参数与测试专用构造器列为 Important 并附 file:line，裁决修复后重审
  - 硬性: 不标 Minor、不以可合入放行
  来源: 2026-09-04 返工（ses_f97eac 找到后标 Minor → ses_f9446b0a 用户要求修复）
```

```
用例 ID: R05
用户处境: 评审含 spec 断言与代码不一致、所及类型 javadoc 与代码矛盾的变更
真实输入: review ey-timp-lab-ai-infra（2026-09-04 现场：parseZip 已拒缺 description 而 spec 只写缺 name；AiRuntimeDependencySyncResultDTO javadoc 称失败进 results、类注释称 WARN，代码走聚合异常打 ERROR）
验收标准:
  - 硬性: 评审者拿到变更所涉 spec/design 路径并对照断言，spec 只写缺 name/代码已拒 description 列为发现
  - 硬性: 所及 javadoc/类注释与代码矛盾列为 Important 并附 file:line，裁决修复后重审，不标 Minor、不以可合入放行
来源: 2026-09-04 返工（c30e601 fix docs；用户：应在开发流程或 review 避免）
```

## 触发测试集

应触发：
- R01 的输入
- 合到主干之前再过一遍
- 进行独立评审（来源：2026-08-05 智能体节点试运行会话原话，ses_02e537f28）

不应触发：
- 给这个函数写单元测试（→ tdd/实现工作）
- 验收标准第二条没过，修一下（→ implement 验证循环）
- 这段代码是干什么的（纯解读，无变更评审）

边界对：
- code-review vs implement：「验证都过了，能归档吗」——归档门禁属 implement 流程，由它派发 code-review，不是 code-review 抢跑
- code-review vs tdd：「测试写得够不够」——补测试是 tdd 侧，评审现有测试质量是 code-review 侧

## 结果记录

| 日期 | 版本 | 用例 | 结果 | 备注 |
|---|---|---|---|---|
| 2026-08-05 | 现版 | R01/R02 | 真实使用佐证 | 智能体节点两次真实评审（新鲜上下文、分级发现、scoped 重审）；非正式回归 |
| 2026-09-04 | 死代码含未引用参数；本任务死代码/测试专用物=Important | R04 | ✓ | 对照改后正文：旧稿 ses_f97eac 找到死参数与测试专用构造器后标 Minor 放行；新稿两者=Important、修复后重审；description 未改，触发集不跑 |
| 2026-09-04 | 所涉断言仍为真；所及注释矛盾=Important | R05 | ✓ | 对照改后正文：旧稿只读代码、规格符合度只对任务清单，c30e601 类问题可合入；新稿派发含 spec/design 路径、断言失真与注释矛盾 Important；R04 分级句保留死代码/测试专用物，触发集不跑 |
