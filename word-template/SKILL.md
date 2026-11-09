---
name: word-template
description: "按显式模板协议、结构化目标投影、证据台账和资产清单确定性填充本地 DOCX/DOTX 模板，适用于条件块、字段默认值和图片/附件插槽。自然语言标记只作辅助入口；不用于 Markdown、通用 Word 编辑、开放式写作或业务规则制定，分别交给 word、writing 或领域 skill。"
---

# Word 模板确定性生成

## 目录

- [意图锚点](#意图锚点)
- [工作流](#工作流)
- [硬规则](#硬规则)
- [授权与交付](#授权与交付)
- [参考资料](#参考资料)

## 意图锚点

本 skill 负责把已有 DOCX/DOTX 模板、结构化目标投影、证据台账和资产清单组合成可复核的 DOCX。渲染阶段只解析显式模板协议和已固化的数据，不根据上下文临时创作正文。

第一版只支持 DOCX/DOTX。Markdown 不在本 skill 的输出范围内。自然语言标记可以辅助发现槽位或编译成显式模板协议，但不能在渲染阶段作为条件或字段来源。

本 skill 与 `word` skill 叠加使用：本 skill 负责模板绑定、投影、预检和确定性规则；`word` 负责 DOCX 包、OOXML、图片关系和本地结构/视觉验证。`writing` 负责需要面向人改写的表达，不能替代字段绑定。

## 工作流

1. **建立运行清单**：确认输入是 DOCX/DOTX，输出是新的 `.docx` 路径；记录模板哈希、目标标识、投影文件、资产清单、渲染器版本和运行标识。输出已存在时默认停止并报告。
2. **检查模板协议**：读取 [template-contract.md](references/template-contract.md)，扫描正文、表格、页眉页脚和支持的对象部件。把自然语言标记转换为显式锚点；重复、孤立、未知、拆分或位于不支持部件的锚点进入预检错误。
3. **准备输入**：读取 [data-contract.md](references/data-contract.md)，加载源文件清单、证据台账、目标投影和默认值。证据引用必须包含文件哈希与段落/表格等结构定位；源文件改变后旧引用失效。
4. **登记资产**：存在图片、视觉观察或其他附件时读取 [asset-contract.md](references/asset-contract.md)。资产只按清单中的 ID、哈希、模式和状态使用；模型输出先固化为观察记录，再进入投影。
5. **执行预检**：在写出目标文件前汇总所有阻塞项。读取 [failure-contract.md](references/failure-contract.md)，输出机器可读的原因、对象、源数据修复路径和渲染失败路径。预检未通过时不写出半成品 DOCX。
6. **确定性渲染**：按投影绑定、源值、声明默认值的顺序解析字段；只使用显式允许的条件、图片和附件关系。未实现的循环或其他扩展在预检阶段失败。渲染写入临时路径并原子交付，不修改原始模板、源文件或证据台账。
7. **验证并交付**：读取 [verification.md](references/verification.md)，先完成结构验证，再生成逐页视觉材料并人工检查。只有视觉检查显式通过，运行清单才进入最终交付状态；任何必需验证失败都将交付状态标为失败，并保留可复核的诊断信息。

## 硬规则

- 每个目标文档使用独立的 `target_projection`，声明目标用途、必需字段、绑定关系和跨文档一致性策略；不对不同目标文档做全局字段替换。
- 模板协议使用受限的显式字段路径和字面量条件，不执行任意代码、脚本或自由文本表达式。
- 默认值可以声明，但必须属于模板协议或目标投影中的唯一生效来源；有源值时默认值不覆盖源值，使用默认值时在运行清单中标记 `declared_default`。
- 字段的 `missing`、`null`、`unknown`、`not_applicable` 和空字符串是不同状态。必填字段缺少可用值且没有有效默认值时，预检失败。
- 图片仅用于插入时不要求 OCR 或视觉理解；图片需要提供语义观察时，可以使用 OCR、视觉模型或人工标注。视觉结果必须审核其台账分类，且只能用于资产归类、证据索引和模板路由，不能直接填充事实字段。
- 视觉观察记录必须保存原图哈希、提取方式、模型或工具版本、提示词哈希（如适用）、输入哈希、置信度和审核状态；渲染器不读取一次性模型回答。
- 附件关系按 [asset-contract.md](references/asset-contract.md) 的能力矩阵处理。无法解码的资产、不支持的嵌入关系和不完整的附件链路必须阻塞渲染。
- 缺字段、缺证据、图片无法读取或附件关系不支持时，报告同时给出两条路径：补充/修改数据源后重跑；若未修复，则渲染失败并给出具体修复建议。系统不静默修改源数据。
- “结构一致”检查锚点、字段、表格、关系、证据和残留标记；“视觉一致”检查固定渲染环境下的页数、分页、表格溢出、图片位置和关键版式，不要求 DOCX 二进制完全相同。
- 同一模板哈希、输入哈希、投影、资产和渲染器版本应产生结构与视觉等价的结果；模型只在渲染前参与数据准备，不能改变渲染规则。

## 授权与交付

默认直接读取、分析模板和源文件，生成新的目标文件及报告。原始模板、源文件、证据台账和资产清单保持不变；需要补充或修改数据时生成修复建议或新的源数据版本，不直接覆盖原件。

交付包至少包含：目标 `.docx`、运行清单、证据/资产使用摘要和验证报告。预检失败或验证失败时只交付失败报告和诊断产物，不把不完整 DOCX 作为成功结果。

随附入口位于 `scripts/render_template.py`。先运行：

```bash
python3 <skill-dir>/scripts/render_template.py preflight \
  --template <template.docx> \
  --projection <target-projection.json> \
  --evidence <evidence-ledger.json> \
  --assets <asset-manifest.json> \
  --report <preflight.json>
```

预检返回非零状态时先处理报告中的错误。预检通过后使用同一组输入运行 `render`，它会交付 `structural_ready` 的 DOCX 和报告。再运行 `verify` 生成 PDF/逐页 PNG，人工检查后带 `--accept-visual` 完成最终交付。不要把预检或结构生成成功当作视觉验证成功。

```bash
python3 <skill-dir>/scripts/render_template.py render \
  --template <template.docx> \
  --projection <target-projection.json> \
  --evidence <evidence-ledger.json> \
  --assets <asset-manifest.json> \
  --output <result.docx> \
  --report <render-report.json>
```

```bash
python3 <skill-dir>/scripts/render_template.py verify \
  --document <result.docx> \
  --report <render-report.json> \
  --visual-output <visual-output-dir>
```

检查 `visual-output-dir` 中的逐页 PNG 后，再使用同一目录运行 `verify --accept-visual`，报告才会进入 `rendered`。

## 参考资料

- [template-contract.md](references/template-contract.md)：显式标记语法、锚点生命周期、Word 部件和不支持的模板形态。
- [data-contract.md](references/data-contract.md)：目标投影、字段状态、默认值和证据定位契约。
- [asset-contract.md](references/asset-contract.md)：图片、视觉观察、表格图像和附件关系契约。
- [failure-contract.md](references/failure-contract.md)：预检错误、两条修复路径和事务性失败行为。
- [verification.md](references/verification.md)：结构一致、视觉一致、运行清单和验证报告。

