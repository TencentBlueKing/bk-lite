# 任务容器使用说明

Python、Shell 和技能 execute 共用 `/workspace`，每次调用是新进程；文件和已安装依赖在本轮内保留，结束后随容器删除。
容量仍为 1 GiB 内存、1 CPU、256 MiB 工作目录、128 MiB 临时目录。工作目录使用 tmpfs，也占用内存。

## 数据分析

- 大 JSON 使用 `ijson.items(stream, 'item')` 逐条读取顶层数组；`{"items": [...]}` 使用 `items.item`。
  先查看少量内容确认实际结构；工具结果不一定是 JSON。
- CSV 使用 `pandas.read_csv(path, chunksize=...)`，JSONL 逐行解析。
- 只累计所需统计量，不把迭代器转成 list，不把所有分块重新 concat。
- 流式解析降低解析内存，但落盘文件仍受 256 MiB 工作目录限制；及时清理自己生成的中间文件。
- HTTP 请求用 requests 或 curl；HTML 解析用 lxml。已有 Python sqlite3、numpy、pandas、matplotlib。

```python
import ijson

with open('/workspace/data.json', 'rb') as stream:
    total = sum(row['value'] for row in ijson.items(stream, 'items.item'))
```

## HTML 与中文 PDF

HTML 用 Jinja2 模板并开启 `Environment(autoescape=True)`；Markdown 用
`MarkdownIt('commonmark', {'html': False})` 转为 HTML。仅对自己生成、可信的 HTML 使用 `safe`。
写入 UTF-8，设置 `<meta charset="utf-8">`。图表复用 matplotlib 输出 PNG/SVG。
当前没有浏览器或 Office 渲染引擎，不能声称已做浏览器截图或页面视觉验证。

PDF 复用 ReportLab，必须显式注册并使用中文字体（正文、标题、表格样式都要设置）：

```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

pdfmetrics.registerFont(TTFont('WQY', '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'))
canvas = Canvas('/workspace/report.pdf')
canvas.setFont('WQY', 14)
canvas.drawString(50, 750, '告警汇总')
canvas.save()
```

可用 `pdftotext` 检查文本、`pdffonts` 检查字体、`pdftoppm` 输出页面图片。
附件格式可用 `file` 判断；打包/解包用 `zip`、`unzip`。解压前查看条目大小，避免超出工作目录容量。
生成文件后用 `generate_attachment_file(filename=..., file_type=..., sandbox_path='/workspace/...')` 保存附件。
当前会话授权附件按 `/workspace/attachments/index.json` 清单，通过其中的读取脚本按需下载。

## 安装额外依赖

系统依赖由镜像提供；任务以非 root 用户执行。Python 使用同一个 `python` 解释器：

```sh
python -m pip install --user <package>
npm install -g <cli-package>
# Node 脚本库安装在脚本所在目录；执行时使用该目录下的脚本。
cd /workspace/your-project && npm install <package>
```

Python 用户包和 npm 全局 CLI 位于 `/workspace/.local`，其 bin 已在 PATH 中。
pip 默认不保留下载缓存；npm 缓存在 `/workspace/.cache/npm`，需要腾出空间时使用 `npm cache clean --force`。
uv 缓存也在工作目录；`uv pip` 通常需要虚拟环境，不要混用安装环境后期待默认 Python 自动找到包。
先使用预装库，额外安装也受本轮时间和磁盘配额限制。
