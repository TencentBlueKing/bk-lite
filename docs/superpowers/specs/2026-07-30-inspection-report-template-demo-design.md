# 巡检报告 Word 模板渲染样例设计

## 目标

验证以下技术路线是否能够稳定生成保留既有版式的巡检报告：

1. 巡检脚本输出结构化 JSON 数据。
2. 用户按照受约束的 Jinja 模板规范编写 DOCX。
3. 通用 Python 程序校验并组合数据、图表与模板。
4. 程序输出可继续编辑的 DOCX 巡检报告。

本次只交付独立可运行样例，不接入作业平台或其他产品模块，也不实现 Excel。

## 交付结构

样例放在 `examples/inspection_report_demo/`：

```text
examples/inspection_report_demo/
├── README.md
├── requirements.txt
├── render_report.py
├── report_data.json
├── report_template.docx
└── output/
    └── inspection_report.docx
```

`report_template.docx` 基于用户提供的《IT资产健康状态巡检报告》制作，保留其主要排版和视觉样式，并覆盖普通变量、条件内容、表格循环以及图表图片替换。

## 技术方案

使用 `docxtpl` 驱动 DOCX 中的 Jinja 模板，使用 Jinja 严格未定义变量模式阻止字段遗漏静默产生空白。图表由 `matplotlib` 生成 PNG，再以 Word 内嵌图片形式注入模板。

`render_report.py` 提供以下命令行接口：

```bash
python render_report.py \
  --template report_template.docx \
  --data report_data.json \
  --output output/inspection_report.docx
```

程序不硬编码报告中的巡检字段。除图表协议使用保留字段 `_charts` 外，其余 JSON 内容原样作为模板上下文。

## 数据协议

数据源使用 UTF-8 编码的 JSON 文件。允许的基础类型为对象、数组、字符串、数字、布尔值和 `null`。字段名使用小写 `snake_case`，业务数值保持数字类型，单位由独立字段或模板负责显示，禁止把所有值预先拼成带单位字符串。

顶层 `_charts` 是可选的图表定义对象。每个键同时是模板变量名，值声明图表类型、标题、标签、数据序列和显示尺寸。首版支持饼图和分组柱状图；未知图表类型、标签与数据长度不一致或非数值数据均视为错误。

示意：

```json
{
  "report": {
    "number": "IT-INSPECT-20260729-001",
    "inspection_date": "2026年07月29日"
  },
  "critical_hosts": [
    {
      "hostname": "DB-Server-01",
      "ip": "192.168.1.10",
      "metric": "磁盘使用率",
      "value": 94,
      "unit": "%"
    }
  ],
  "_charts": {
    "health_distribution_chart": {
      "type": "pie",
      "title": "IT资产健康状态分布",
      "labels": ["正常", "预警", "严重", "离线"],
      "values": [128, 15, 5, 2],
      "width_inches": 5.5
    }
  }
}
```

## 模板规范

- 普通变量使用 `{{ variable }}`。
- 条件使用 Jinja 的 `if` 语法。
- 重复表格行使用 `docxtpl` 的表格行标签，控制标签各自独占模板行。
- 图表位置使用与 `_charts` 键同名的变量。
- 一个模板标签必须完整位于同一 Word 段落或单元格的同一文本运行中，避免 Word 将语法拆分后无法识别。
- 模板只使用样例明确开放的变量、条件、循环和过滤器，不得执行任意 Python 代码或访问进程环境。
- 首版不支持任意已有 DOCX 的自动数据绑定、Word 原生可编辑图表、自动目录页码更新和 Excel 模板。

## 渲染流程

1. 校验输入、输出路径以及 JSON 根节点类型。
2. 读取 JSON，并以明确错误报告解析失败位置。
3. 校验 `_charts`，在临时目录中生成 PNG。
4. 将图表转换为 DOCX 内嵌图片对象并加入模板上下文。
5. 以严格未定义变量模式渲染模板。
6. 将结果写入调用方指定路径。
7. 无论成功或失败都清理临时图表文件。

输出目录可由程序创建，但不会覆盖模板或数据源。输出文件已存在时允许原子替换，渲染失败时不得留下半成品。

## 错误处理与安全边界

- JSON 无效、顶层不是对象、字段缺失、模板语法错误和图表协议错误均返回非零退出码和面向用户的错误说明。
- 图表数量、单个序列数据点数量和图片尺寸设置合理上限，避免不受控资源消耗。
- 图表标题和标签只作为文本处理。
- 模板渲染使用受限环境，不向模板暴露 Python 模块、文件系统、环境变量或任意可调用对象。
- 本样例证明模板化路线和格式保持能力，不等同于生产级多租户模板执行沙箱。

## 验证

实现完成后执行以下新鲜验证：

1. 使用随附 JSON 和 DOCX 模板成功生成报告。
2. 解包输出 DOCX，确认文件结构有效、模板标签已消失且图表图片已嵌入。
3. 使用 LibreOffice 将结果转换为 PDF。
4. 渲染 PDF 页面，人工检查封面、循环表格、分页、中文字体和图表。
5. 使用缺失字段、无效 JSON 和错误图表定义验证失败路径不会生成半成品。

成功标准是：示例命令可重复执行；输出报告可被 Word/LibreOffice 打开；主要样式得到保留；数据行和图表来自 JSON；错误输入得到明确拒绝。
