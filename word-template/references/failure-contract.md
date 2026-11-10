# 预检失败契约

## 目录

- [状态](#状态)
- [错误对象](#错误对象)
- [错误分类](#错误分类)
- [两条修复路径](#两条修复路径)
- [事务性行为](#事务性行为)

## 状态

渲染运行只能进入以下状态：

```text
ready       预检通过，可以渲染
blocked     输入、模板或资产存在阻塞问题
failed      渲染或验证执行失败
structural_ready  DOCX 已生成且结构检查通过，等待视觉检查
visual_ready      已生成逐页视觉材料，等待人工视觉验收
rendered    渲染、结构检查和视觉验收均通过
```

## 错误对象

每个阻塞项至少包含：

```json
{
  "code": "FIELD_REQUIRED_MISSING",
  "severity": "blocking",
  "object_id": "project.name",
  "reason": "没有有效绑定值、证据或默认值",
  "source_fix": "补充或修改数据源后生成新的源数据版本",
  "render_fix": "保持当前输入时停止渲染，并在修复后重新预检"
}
```

## 错误分类

实现至少区分以下代码：

```text
TEMPLATE_MARKER_UNKNOWN
TEMPLATE_MARKER_SPLIT
TEMPLATE_BLOCK_UNSUPPORTED
TEMPLATE_BLOCK_UNMATCHED
TEMPLATE_FORMAT_UNSUPPORTED
TEMPLATE_PART_UNSUPPORTED
TEMPLATE_UNREADABLE
PROJECTION_UNREADABLE
PROJECTION_INVALID
EVIDENCE_LEDGER_UNREADABLE
ASSET_MANIFEST_UNREADABLE
OUTPUT_EXISTS
OUTPUT_ALIASES_INPUT
FIELD_NOT_BOUND
FIELD_REQUIRED_MISSING
FIELD_STATE_UNUSABLE
FIELD_STATE_INVALID
DEFAULT_CONFLICT
FORMAT_UNSUPPORTED
FORMAT_VALUE_INVALID
EVIDENCE_NOT_FOUND
EVIDENCE_STALE
EVIDENCE_LOCATOR_INVALID
ASSET_NOT_FOUND
ASSET_HASH_MISSING
ASSET_HASH_MISMATCH
ASSET_UNREADABLE
ASSET_MEDIA_TYPE_MISMATCH
ASSET_REFERENCE_MISSING
ASSET_MANIFEST_INVALID
EVIDENCE_REJECTED
VISUAL_OBSERVATION_UNREVIEWED
VISUAL_OBSERVATION_PROVENANCE_MISSING
VISUAL_FIELD_NOT_ALLOWED
ATTACHMENT_RELATION_UNSUPPORTED
RENDER_VERIFY_FAILED
```

错误代码对应的修复建议必须指向模板、数据、资产、投影或适配器中的实际对象，不能只写“请检查输入”。

## 两条修复路径

遇到缺字段、缺证据、图片无法读取或附件关系不支持时，报告同时展示：

1. **补充或修改数据源**：补齐字段、重新导出可读资产、把附件转换成支持的关系，或生成带新哈希的新源数据版本；原始文件不被静默覆盖。
2. **渲染失败**：保留当前输入和错误证据，不生成成功状态的 DOCX，并列出修复对象、建议动作和重新运行条件。

当问题属于模板部件或适配器能力不足时，第一条路径可以是把源附件转换为支持格式；转换仍不可行时只能走第二条路径。

## 事务性行为

预检在写出目标文件之前完成。报告路径不得与模板、投影、证据台账、资产清单或 DOCX 输出同路径；冲突时返回 `OUTPUT_ALIASES_INPUT`，不写入任何输入或输出。渲染和验证使用临时路径；验证失败时删除或隔离临时目标，不把它登记为交付物。报告、日志和源哈希保留，便于修复后重跑。

