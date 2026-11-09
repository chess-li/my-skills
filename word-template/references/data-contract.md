# 数据与证据契约

## 目录

- [输入组成](#输入组成)
- [目标投影](#目标投影)
- [字段解析](#字段解析)
- [证据定位](#证据定位)

## 输入组成

完整材料准备通常包含以下文件；渲染入口按模板中实际引用的内容读取它们：

```text
template.docx 或 template.dotx
source-inventory.json
evidence-ledger.json
target-projection.json
asset-manifest.json
```

`source-inventory` 记录源文件路径、类型、版本、哈希和可读性，属于上游材料清单；`evidence-ledger` 记录结构化证据；`target-projection` 记录目标用途和字段绑定；`asset-manifest` 记录图片、表格图像和附件。没有证据、图片或附件引用时，相应清单可以省略，但不能用省略清单掩盖模板中的实际引用。

核心对象可以扩展领域字段，但不能把某个业务场景的字段名写死在 skill 中。

## 目标投影

目标投影必须声明非空 `target_id`；完整投影还应声明版本、用途、绑定、默认值和策略：

```json
{
  "schema_version": "1.0",
  "target_id": "target-001",
  "purpose": "由调用方定义",
  "bindings": {
    "project.name": {"source": "evidence:e-001"},
    "project.date": {"source": "evidence:e-002", "format": "YYYY-MM-DD"}
  },
  "defaults": {
    "project.owner": "未提供"
  },
  "policies": {
    "consistency": []
  }
}
```

不同目标文档可以绑定不同名称、日期、预算或其他字段。跨文档一致性只有在 `policies.consistency` 中显式声明时才检查。

## 字段解析

字段解析顺序固定为：

1. 目标投影中的有效绑定值；
2. 绑定证据中的已读取值；
3. 字段状态为 `missing` 或未声明状态时，才使用唯一生效来源中的声明默认值；
4. 仍无值则按字段状态判定为阻塞或可选空值。

字段状态必须区分：

```text
missing          没有找到来源
null             来源明确给出空值
unknown          来源存在但不能确定
not_applicable   对当前目标不适用
empty            来源给出空字符串
```

必填字段只能使用有效绑定值或已声明默认值。`unknown`、`null`、`not_applicable` 和 `empty` 是已有来源状态，不会静默回退到默认值；它们用于必填字段时预检失败。默认值不创建证据引用，并在运行清单中标注 `declared_default`。

模板级 `default` 在编译到投影后成为投影默认值。模板和投影对同一字段声明不同默认值时，预检失败。

## 证据定位

每条证据至少保存：

```json
{
  "evidence_id": "e-001",
  "source_file": "source.xlsx",
  "source_sha256": "...",
  "locator": {"kind": "paragraph", "index": 12},
  "normalized_text_sha256": "...",
  "value": "...",
  "status": "machine_readable"
}
```

表格使用表格、行、列索引；图片使用资产 ID 和媒体哈希。源文件哈希或定位文本改变后，证据状态变为 `stale`，不能继续绑定。

