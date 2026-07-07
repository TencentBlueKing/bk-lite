# 监控告警多指标公式问题优化设计

## 背景

多指标公式功能已合入 master。审查发现三类需要发布前收口的问题：

- 指标编辑器布局错乱，新增/配置指标时控件挤压，影响策略配置主流程。
- 公式 anchor 规则前后端不一致：后端按表达式首变量，前端按第一行指标，可能导致预览/保存语义不一致。
- 公式预览追加资产过滤时，把实例过滤直接追加到 filter 尾部；遇到 OR 条件时，实例过滤只作用在最后一个 OR 分支，预览可能混入非选中资产数据。

本次优化只覆盖多指标公式相关路径，保持单指标 `query_condition.type=metric` 旧结构和旧行为不变，不新增普通策略 PromQL 创建入口，Trap PMQ 旧入口保留。

## 目标

1. 让指标编辑器在新增、删除、空指标、双指标公式等状态下布局稳定，可完成策略配置。
2. 统一公式最终维度来源，避免表达式变量顺序改变 anchor。
3. 让公式预览资产过滤与单指标预览的 AND/OR 语义一致。
4. 补齐 focused 测试，覆盖本次审查发现的风险场景。

## 非目标

- 不重做策略创建页面整体流程。
- 不调整告警扫描调度、通知、恢复逻辑。
- 不引入新的 PromQL/MetricQL 编辑入口。
- 不处理主工作区已有历史脏文件。

## 方案选择

采用完整收口方案：同时修 UI 阻断、anchor 规则、公式预览资产过滤，并补测试。

不采用只修 UI 的临时方案，因为 anchor 与预览过滤会继续留下隐性错误；不采用只修后端语义的方案，因为编辑器布局已经影响主流程配置。

## UI 设计

调整 `MetricExpressionEditor` 的结构和样式，保持现有状态字段不变。

指标编辑器面板：

- 外层显示轻量面板，标题栏包含“指标编辑器”和“表达式”标签。
- 面板宽度跟随表单区域，内部控件不得横向溢出。
- 保持 6px 左右圆角和现有 BK-Lite 表单视觉，不引入新的设计系统。

指标行：

- 每个指标用一张轻量行卡片承载。
- 主行使用稳定 grid：变量 badge、指标 Select、聚合 Select、group_by Select、删除按钮。
- 指标 Select 和 group_by Select 使用明确的 `minmax` 约束；窄宽度时允许自然换行，不遮挡按钮。
- 聚合 Select 展示为 `sum by` / `avg by` 这类完整语义，避免旁边再放一个孤立 `by` 文本导致错位。
- 变量 badge 使用窄蓝色标签，显示 `a`、`b`、`m27` 等变量名。

条件行：

- 条件行缩进到指标主行下方。
- 第一条显示“条件”，后续显示 AND/OR Select。
- 条件行列为：逻辑/标题、label、operator、value、删除按钮。
- `添加条件` 按钮放在条件列表下方，左侧与条件内容对齐。

新增指标与公式行：

- `添加指标` 按钮放在指标卡片列表下方，使用中文文案和加号图标。
- 修复文案 key 未解析时显示 `monitor.events.addMetric` 的问题；优先确认 i18n namespace，必要时使用当前页面已生效的 key。
- 公式模式下底部固定显示 `fx` 行：`fx badge`、`result_name`、`=`、`expression`。
- 删除指标后，表达式引用不存在变量时继续给出校验错误，不自动猜测替换表达式。

## Anchor 规则

统一以 `query_condition.queries[0].ref` 作为公式 anchor。

具体规则：

- 后端 `validate_formula_condition` 不再用表达式中第一个出现的变量作为 anchor。
- 后端校验非 anchor 指标的 `group_by` 必须是 anchor `group_by` 的子集。
- 后端编译完成后，最终公式结果 `group_by` 必须等于 anchor `group_by`。
- 前端预览、payload 构建、展示均以第一行指标作为 anchor。
- 表达式 `a / b`、`b / a`、`(b / a) * 100` 不改变最终告警身份/维度，最终维度始终来自第一行指标。

该规则与 UI 模型一致：第一行指标是公式结果维度的来源。

## 预览资产过滤

公式预览的实例过滤必须作为公共过滤条件作用于每个 OR 分支。

推荐实现：

- 后端公式编译支持按 ref 传入 `base_filters_by_ref`。
- `FormulaCompiler._compile_variable` 调用 `compile_filter_to_query(metric.query, filter, base_filters)`。
- `PolicyPreviewService` 在公式预览时，根据每个查询指标的 `instance_id_keys` 和 `preview.instance_id_values` 构造 `base_filters_by_ref`。
- 前端不再把预览实例过滤直接 append 到 `query_condition.queries[].filter` 尾部。

示例：

用户条件为 `service="checkout" OR status="500"`，预览资产为 `instance_id="host-1"`。

编译结果应等价于：

- `(metric{instance_id=~"host-1", service="checkout"})`
- `or`
- `(metric{instance_id=~"host-1", status="500"})`

不得生成：

- `(metric{service="checkout"}) or (metric{status="500", instance_id=~"host-1"})`

## 单指标兼容

单指标策略继续使用旧结构：

```json
{
  "type": "metric",
  "metric_id": 1,
  "filter": []
}
```

单指标预览继续使用现有 `base_filters` 路径，不改变现有 AND/OR 编译语义。

## 错误处理

- anchor 校验失败、表达式非法、指标缺失继续返回受控 `BaseAppException` / serializer validation error，避免 500。
- 公式预览缺少指标、缺少实例、缺少算法时保持现有前端校验提示。
- UI 文案未命中 i18n key 时不得展示原始 key；需回退为明确中文文案。

## 测试设计

后端 focused 测试：

- `test_formula_validator.py`：新增表达式顺序不影响 anchor 的用例，`queries[0]=a` 且表达式 `b / a` 时 anchor 仍为 `a`。
- `test_formula_compiler.py`：新增 `b / a` 场景，最终 group_by 等于第一行指标 group_by，MetricsQL modifier 方向正确。
- `test_formula_policy_preview.py`：新增 OR 条件 + 资产过滤用例，断言每个 OR selector 都带实例过滤。
- `test_formula_policy_scan.py`：保留最终公式结果 group_by、无数据基准、无数据告警测试。

前端 focused 测试：

- `web/scripts/monitor-policy-formula-payload-test.ts`：覆盖新增指标、删除变量后的校验、`b / a` payload、公式预览不直接 append 实例过滤。
- focused eslint 覆盖 `formulaExpressionUtils.ts`、`metricExpressionEditor.tsx`、`metricDefinitionForm.tsx`、`metricPreview.tsx`、`page.tsx`。

手工验收：

- 新建策略默认单指标空态不挤压。
- 点击“添加指标”后进入公式模式，两个指标行与 fx 行布局稳定。
- 删除第二个指标后校验提示清晰，不出现控件错位。
- 带 OR 条件的公式预览只展示所选资产数据。

## 验收标准

- 指标编辑器视觉接近参考图，控件无遮挡、无横向溢出、按钮文案正确。
- 表达式变量顺序不影响最终告警身份/维度。
- 公式预览与单指标预览的 AND/OR + 资产过滤语义一致。
- 单指标旧 payload、扫描、预览行为不变。
- focused 后端测试、前端脚本测试、focused eslint 通过。

## 风险与回滚

- UI 重排风险：Ant Design Select 宽度与响应式行为可能在不同容器下表现不同。通过固定 grid 轨道和手工截图验收降低风险。
- Anchor 规则变更风险：已有公式策略如果依赖“表达式首变量”为 anchor，行为会变化。由于 UI 一直以第一行作为主指标，此变更是纠偏；需要在测试中覆盖历史策略编辑回填。
- 预览编译参数风险：公式编译器新增可选 base filters 时必须保持默认值为空，避免影响扫描路径。

回滚方式：

- UI 可单独回滚 `MetricExpressionEditor` 布局变更。
- Anchor 与预览过滤变更需连同对应测试一起回滚，避免前后端规则再次不一致。
