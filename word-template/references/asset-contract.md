# 资产与视觉观察契约

## 目录

- [资产模式](#资产模式)
- [视觉观察](#视觉观察)
- [附件关系](#附件关系)
- [可读性边界](#可读性边界)

## 资产模式

本地资产清单中的每个对象至少包含 ID、原始路径、文件哈希、媒体类型和模式；`external_reference` 使用 `reference` 代替本地路径，可由调用方另行提供内容哈希：

```json
{
  "asset_id": "image-001",
  "path": "images/result.png",
  "sha256": "...",
  "media_type": "image/png",
  "mode": "asset_only",
  "status": "ready"
}
```

支持的模式由适配器声明。常见模式如下：

- `asset_only`：只验证文件可读取、类型和尺寸，然后按模板插入；不要求 OCR 或视觉理解。
- `visual_observation`：使用 OCR、视觉模型或人工标注形成结构化观察记录；观察记录必须固化后才能被投影引用。
- `table_image`：把已登记的表格或图表图像作为资产插入，不从图像反推数值。
- `appendix_file`：把支持的附件复制到 DOCX 旁的 `<output>.attachments/` 交付目录，并在运行清单中建立资产 ID 到文件的附录关系；不等同于 OLE 嵌入。
- `external_reference`：只写入已登记的外部引用；路径或 URL 缺失时失败。

## 视觉观察

视觉观察记录至少包含：

```json
{
  "observation_id": "obs-001",
  "asset_id": "image-001",
  "extractor": {
    "kind": "vision_model",
    "model": "model-id",
    "prompt_sha256": "..."
  },
  "input_sha256": "...",
  "observations": [{"key": "ledger_category", "value": "...", "confidence": 0.91}],
  "review": {"required": true, "scope": "ledger_classification", "status": "approved"},
  "semantic_status": "unverified"
}
```

视觉结果必须审核其是否进入合适的台账分类。分类审核不等同于独立事实核验；因此 `semantic_status: unverified` 的观察结果只能用于资产归类、证据索引和模板路由，不能直接填充目标事实字段。

模型输出可以来自支持图片理解的模型，不要求先经过 OCR。模型回答必须先转换为上述观察记录，不能在渲染时直接读取对话文本。

## 附件关系

`attachment` 标记只能引用清单中的资产 ID。第一版优先支持原始文件作为旁路附录或已登记外部引用；复杂 OLE、宏、嵌入式工作簿、动态链接和未声明的关系类型不自动转换。旁路附录不是 DOCX 内嵌对象，交付时必须连同 `<output>.attachments/` 一起保留。

若源文件可以转换为支持的图片、PDF 或附录文件，可以把转换后的文件作为新的源数据版本重新登记。不能用修改模板文字来掩盖不支持的附件关系。

## 可读性边界

- 文件无法解码、媒体类型与扩展名冲突或哈希无法计算：阻塞所有使用该资产的目标。
- 文件可以插入但不能理解：`asset_only` 可以继续；需要 `visual_observation` 时阻塞。
- 观察结果存在但审核仍为 `pending` 或 `rejected`：阻塞依赖该观察结果的分类或字段绑定。
- 当适配器或资产记录声明了尺寸、比例或分辨率约束且图片不满足时，阻塞渲染并建议提供新资产或调整模板插槽；未声明约束时不猜测版式要求。

