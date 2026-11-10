# Word 本地替代工具

这些工具都在本机处理文件，skill 通过路径把它们串起来：

## 平台矩阵

| 平台 | Python/TXT/CSV/OOXML | LibreOffice | Poppler | Pandoc |
| --- | --- | --- | --- | --- |
| 通用 Linux | 支持 | `soffice` 或 `libreoffice` 在 `PATH` | `pdftoppm` 在 `PATH` | `pandoc` 在 `PATH` |
| macOS | 支持 | 支持 `.app` 内的 `soffice` 或 `PATH` 命令 | `pdftoppm` 在 `PATH` | `pandoc` 在 `PATH` |
| Windows | 支持 | `soffice.com`/`soffice.exe` 在 `PATH` 或标准安装目录 | `pdftoppm.exe` 在 `PATH` | `pandoc.exe` 在 `PATH` |

`office/soffice.py` 负责发现三平台的 LibreOffice 可执行文件；Linux 沙箱 shim 只在 Linux 使用，Windows 不读取 `LD_PRELOAD`。外部工具仍由调用方安装，skill 不把某个平台的安装目录写死为唯一入口。

| 能力 | 本地工具 | 调用入口 | 分发提示 |
| --- | --- | --- | --- |
| DOC/DOCX/DOTX → PDF | LibreOffice | `scripts/render_docx.py` | 输出使用独立新目录；`--force` 只替换该目录，不删除同名兄弟目录或历史备份。LibreOffice 以 MPL 2.0 发布，提供 Windows、macOS 和 Linux 安装包。 |
| PDF → 逐页 PNG | Poppler `pdftoppm` | `scripts/render_docx.py` | Poppler 是开源 PDF 渲染库；只读取本地 PDF。 |
| Markdown → DOCX 与引用 | Pandoc + citeproc | `scripts/md2docx_citeproc.py` | Pandoc 支持 BibTeX/BibLaTeX、CSL JSON/YAML 和 RIS；引用键使用 `[@key]`。 |
| DOCX 创建 | `python-docx` 或 bundled `docx` npm 包 | `scripts/docx_tool.py`、`scripts/docx.py` | Python 包需要时使用 `pip3 install python-docx`；Node 包由调用方项目或 skill 的 bundled 运行时提供。 |

Pandoc 的 bibliography 文件、CSL 样式、图片和参考模板都必须是调用方可读的本地路径。没有 `pandoc`、LibreOffice 或 Poppler 时，脚本报告缺失依赖，不把结构检查冒充视觉验证。

参考：

- LibreOffice：<https://www.libreoffice.org/licenses/>、<https://www.libreoffice.org/download/>。
- Pandoc 手册（`--citeproc`、`--bibliography`）：<https://pandoc.org/MANUAL.html>。
- Poppler：<https://poppler.freedesktop.org/>。
