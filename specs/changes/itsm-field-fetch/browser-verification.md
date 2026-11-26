# 全字段页面取数验收（2026-11-16）

## 验收方式

使用本地 3000 前端、8000 Django 和真实 Python Runner，在流程设计器逐字段切换来源、选择资源、配置路径/列映射、点击“测试取数”，读取页面返回结果。另检查预览选择与回填。没有用接口测试替代此表中的页面操作。

独立测试草稿：[Review] 全字段页面验收，流程 ID 7，表单 ID 5；未发布。

## 页面发现并修复的问题

1. 单选框切换 API 默认 label/value 与平台 data.items + title/id 不匹配。未填路径时识别明确的常见列表容器和名称/值键；显式映射仍严格执行。切换 API 清理旧路径。
2. 取数错误被统一边界吞掉具体原因。字段调试接口返回具体校验信息，页面验证 wrong.items 报错后清空路径可恢复。
3. 级联与普通选项共用缓存导致子节点消失。凭据和缓存加入字段类型，页面复测两种级联均保留 children。
4. 流程设计预览未传取数上下文。已接通授权预览取数，验证下拉/单选/复选、级联子项选择，以及文本数值和表格回填。

## 有效来源组合（37 项）

| 字段 | 来源 | 页面结果 |
|---|---|---|
| input | python | 通过：`"页面验收文本"` |
| textarea | python | 通过：`"页面验收文本"` |
| number | python | 通过：`42` |
| radio | python | 通过：`[{"value": "a", "label": "页面验收选项"}]` |
| checkbox | python | 通过：`[{"value": "a", "label": "页面验收选项"}]` |
| select | python | 通过：`[{"value": "a", "label": "页面验收选项"}]` |
| multiselect | python | 通过：`[{"value": "a", "label": "页面验收选项"}]` |
| table | python | 通过：`[{"name": "页面验收文本", "amount": 42}]` |
| nestedTable | python | 通过：`[{"name": "页面验收文本", "amount": 42}]` |
| radio | api | 通过：`[{"value": 40, "label": "字段 API 数据样本"}]` |
| checkbox | api | 通过：`[{"value": 40, "label": "字段 API 数据样本"}]` |
| select | api | 通过：`[{"value": 40, "label": "字段 API 数据样本"}]` |
| multiselect | api | 通过：`[{"value": 40, "label": "字段 API 数据样本"}]` |
| cascade | api | 通过：`[{"value": 40, "label": "字段 API 数据样本"}]` |
| multiCascade | api | 通过：`[{"value": 40, "label": "字段 API 数据样本"}]` |
| input | api | 通过：`"字段 API 数据样本"` |
| textarea | api | 通过：`"字段 API 数据样本"` |
| number | api | 通过：`1` |
| table | api | 通过：`[{"name": "字段 API 数据样本", "amount": 40}]` |
| nestedTable | api | 通过：`[{"name": "字段 API 数据样本", "amount": 40}]` |
| radio | dictionary | 通过：`[{"value": "a", "label": "页面验收选项"}, {"value": "b", "label": "页面验收子项"}]` |
| checkbox | dictionary | 通过：`[{"value": "a", "label": "页面验收选项"}, {"value": "b", "label": "页面验收子项"}]` |
| select | dictionary | 通过：`[{"value": "a", "label": "页面验收选项"}, {"value": "b", "label": "页面验收子项"}]` |
| multiselect | dictionary | 通过：`[{"value": "a", "label": "页面验收选项"}, {"value": "b", "label": "页面验收子项"}]` |
| cascade | dictionary | 通过：`[{"value": "a", "label": "页面验收选项", "children": [{"value": "b", "label": "页面验收子项"}]}]` |
| multiCascade | dictionary | 通过：`[{"value": "a", "label": "页面验收选项", "children": [{"value": "b", "label": "页面验收子项"}]}]` |
| radio | table | 通过：`[{"value": "a", "label": "页面验收选项"}]` |
| checkbox | table | 通过：`[{"value": "a", "label": "页面验收选项"}]` |
| select | table | 通过：`[{"value": "a", "label": "页面验收选项"}]` |
| multiselect | table | 通过：`[{"value": "a", "label": "页面验收选项"}]` |
| input | table | 通过：`"页面验收文本"` |
| textarea | table | 通过：`"页面验收文本"` |
| number | table | 通过：`42` |
| table | table | 通过：`[{"name": "页面验收文本", "amount": 42}]` |
| nestedTable | table | 通过：`[{"name": "页面验收文本", "amount": 42}]` |
| cascade | python | 通过：`[{"value": "a", "label": "页面验收选项", "children": [{"value": "b", "label": "页面验收子项"}]}]` |
| multiCascade | python | 通过：`[{"value": "a", "label": "页面验收选项", "children": [{"value": "b", "label": "页面验收子项"}]}]` |

## 专用字段（26 类）

以下字段逐个打开属性面板，确认无通用取数入口，且预览保持专用组件；本表不表示对附件存储、CMDB 数据维护等既有业务完成了全链路验收。

associateConfig、attachment、cab、calculate、cmdb、date、dateRange、datetime、description、divider、group、link、multiCmdb、multiUser、multiUserGroup、organization、richtext、section、signature、singleAssociateConfig、subProcessForm、tab、task、time、user、userGroup

## 页面交互与异常恢复

- 单选、复选、单/多下拉可选中取数结果。
- 单/多级联展开并选择子项，保留名称回显。
- 文本、数值和两类表格回填内容与调试结果一致，文本允许手动修改。
- 错误路径显示“结果缺少字段路径：wrong.items”；清空后取数成功。
- UI 校验截图：`itsm-radio-api-verified.jpg`；完整预览截图：`itsm-all-fields-preview.jpg`。
