# OpsPilot 附件文档主题

Status: ready

## Problem Statement

OpsPilot 生成的 Word、PDF 和 Excel 看起来像把 Markdown 或 CSV 原样倒进文件。正文没有段落节奏，表格没有表头样式，Excel 不能声明合并单元格，PDF 也没有页眉和页码。

## Solution

模型仍然提交 Markdown 或 CSV。服务器把 Markdown 解析成同一份文档结构：HTML/CSS 负责排版，并由服务器里的 Chromium 打印成 PDF；同一份结构写成带标题、正文和表格样式的 docx。Excel 按同一套颜色和字体写入一张工作表，表头自动套样式，合并范围由模型显式声明。用户下载到的是 docx、pdf、xlsx。沙箱里已经写好的文件原样交付。

## User Stories

1. As a user asking for a report, I want the Word or PDF to use headings, paragraph spacing, styled tables, a title header and page numbers, so that the file looks like a document rather than exported notes.
2. As a user asking for a spreadsheet, I want the first header row frozen, filled and bold, with real numbers right-aligned, so that I can filter and calculate without reformatting.
3. As a user asking for a merged title or grouped header, I want to pass the merge ranges and header row count, so that the sheet shows that structure only when I asked for it.
4. As a user asking for an official letter, I want the title and the body on the first page, without the operations-report cover or a contents page, so that a notice does not look like an analysis report.
5. As a user asking for meeting minutes, I want the meeting title, time, place, host and recorder up front, then attendance, topics, decisions and actions, so that the file reads as minutes.
6. As a user who already had the agent write a finished file in the sandbox, I want that file delivered unchanged, so that custom layout is not rewritten.

## Implementation Decisions

- One visual system: white page, near-black text `#212121`, 微软雅黑. The model picks one of three genres. `business_report` is the default for analysis and inspection. Its cover starts with the 12pt eyebrow `运维分析报告` in `#1565C0`, then a 26pt `#1A237E` title, a 14pt `#616161` summary, and 10.5pt lines for 数据来源, 查询时间 and 报告版本. `official` is for 公文、函、请示 and 通知. It puts a centered 22pt title on the first page and does not add the report eyebrow or a contents page. `meeting_minutes` uses the eyebrow `会议纪要` and the lines 会议时间, 会议地点, 主持人 and 记录人, on the same first page as the body, with no contents page. Body headings are 16pt `#1A237E`, 14pt `#1565C0`, then 12pt `#212121`, with no bar and no underline. Word and PDF table headers use `#F5F7FA`, bold `#1A237E` text, and `#E0E0E0` cell borders. Excel keeps the blue header fill `#E3EBFD` and ignores genre. Links are `#1565C0` and underlined. The body header is the document title and the footer is `第 n 页`, starting at 1. A report cover and its contents page have no running header. Official documents and minutes leave the first-page header blank and still print the page number.
- A business report starts with a cover page, then a contents page, then the body. Short paragraphs and the three source lines before the first body heading stay on the cover. The contents page lists body headings through level 3. Word uses a dot leader and a page number counted from the first body page, stored in a PAGEREF field so it can refresh. PDF lists the same headings without leaders or page numbers. Those lines sit flush with the contents title, and only third-level entries indent. A model-written「封面」or「目录」section is dropped so it is not repeated. A heading named 核心结论 or 执行摘要, and the blocks under it until the next heading of the same or higher level, render as a callout. Inside that callout, the first two bold runs that are only a number or a percent render in `#C62828`. Other bold text stays `#212121`. Meeting minutes use the same callout for a heading named 决议, without the red numbers.
- Markdown is parsed once into headings, paragraphs, lists, tables, bold, code and links. Images keep their alt text. Blockquotes become paragraphs. Nested lists flatten into one level.
- Word and PDF share that structure. PDF is HTML/CSS printed by the server Chromium (`EXECUTABLE_PATH` when set). If Chromium cannot print, PDF generation fails and does not fall back to the old plain PDF. Word writes real heading, body and table styles from the same structure, including a page-number field.
- Genre is the tool parameter, `business_report` by default. Body text is 10.5pt. Body paragraphs use a 21pt first-line indent, no left indent, and 1.6 line spacing. Reports and minutes keep 7.2pt after each paragraph. Official documents tighten that gap. Callout paragraphs drop the first-line indent. The report contents page uses 1.5 line spacing. Third-level entries indent 21pt.
- Table columns in Word and PDF take width from the amount of text, with a floor, and wrap inside the cell. Each table keeps 10pt of space above and below.
- Excel is one CSV sheet. `header_rows` defaults to 1. The last of those rows is the column header (fill, bold, frozen underneath). Rows above it are titles without the header fill. `merges` is a list of A1 ranges. A missing list does not merge. A range that does not fit the sheet fails the generation. Integers and decimals become numbers and align right. Other cells stay text.
- Word and PDF ignore `header_rows` and `merges`.
- PPT stays on the current title-and-bullet slides.
- Unsafe link targets are shown as text and are not written as hyperlinks.
- Office and browser libraries stay imported inside the render functions so process startup does not load them.

## Testing Decisions

- Test the bytes the user would download: docx styles, HTML used for PDF, and xlsx cell types, fill, freeze and merges.
- PDF printing is a seam. Tests cover the HTML and the failure log without launching a browser. The failure log records the error type and keeps the document body out of the message.
- Existing attachment tests cover plain-text files, slide splitting, and sandbox files delivered byte for byte.
- A launch-time import check keeps python-docx, openpyxl, python-pptx, reportlab and Playwright off the module top level.

## Out of Scope

- Restyling PPT, images, charts, multiple sheets, and pivot tables.
- Rewriting files delivered from the sandbox.
- Converting HTML bytes into docx with an external converter.
- Guessing dates, percentages, currency, or merge ranges from repeated cell text.

## Further Notes

The brand blue matches the product token `--color-primary` fallback `#155aef`. PDF font selection prefers 微软雅黑 and then the fonts Chromium already has on the server.
