# PowerPoint 本地替代工具

云端演示文稿的创建、读取和发布由以下本地路线覆盖：

这些 Python/OOXML 路线在通用 Linux、macOS 和 Windows 上共用。视觉预览要求本机有 LibreOffice 与 Poppler：Windows 使用 `soffice.com`/`soffice.exe`、`pdftoppm.exe`，macOS/Linux 使用对应的 Unix 命令；把它们加入 `PATH` 后脚本会自动发现。

| 场景 | 本地路线 | 适用范围 |
| --- | --- | --- |
| 新建或大范围生成 | `python-pptx` 或 PptxGenJS | 直接生成标准 OOXML `.pptx`，可在无 PowerPoint 的机器上运行。 |
| 保留未建模部件的局部编辑 | ZIP/XML OOXML 定点编辑 | 备注、批注、母版、嵌入工作簿和扩展部件；使用 `scripts/surgical/`。 |
| 本地预览 | LibreOffice → PDF → Poppler PNG | 逐页检查文字溢出、重叠、字体回退和图表标签。缩略图输出已存在时停止，不覆盖。 |
| 工作副本发布 | `scripts/surgical/request_fold.py` | `--source`、`--target` 或 JSON 操作文件；原子复制并校验 SHA-256。 |

Python 路线需要依赖时使用 `pip3 install python-pptx`。PptxGenJS 和 LibreOffice 由调用方按其本机包管理器安装；技能不需要账号、浏览器会话或桌面 IPC。生成后要用本地 OOXML/结构检查和逐页渲染共同验证。

参考：

- `python-pptx`：<https://python-pptx.readthedocs.io/en/stable/>、<https://github.com/scanny/python-pptx/blob/master/pyproject.toml>。
- PptxGenJS：<https://github.com/gitbrent/PptxGenJS/blob/master/README.md>、<https://github.com/gitbrent/PptxGenJS/blob/master/package.json>。
- Poppler：<https://poppler.freedesktop.org/>。
