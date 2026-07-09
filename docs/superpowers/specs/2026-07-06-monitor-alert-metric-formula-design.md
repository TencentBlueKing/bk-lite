# 监控告警策略指标表达式设计

日期：2026-07-06
状态：已确认设计
范围：bk-lite 监控告警策略的“定义指标”步骤

## 背景

当前监控告警策略是单指标模型：策略通过 `query_condition.type = metric` 指向一个指标，再使用条件维度、分组聚合方式、分组维度、策略级聚合周期、策略级聚合方式和阈值完成评估。

该模型可以覆盖 CPU、内存、磁盘、网络等单指标告警，但不能直接表达成功率、错误率、容量使用率、队列净积压等多指标计算场景。目标是在普通策略页面中把“指标”配置升级为指标表达式编辑器，支持单指标、多指标、过滤、分组和公式计算，同时不把用户暴露到 PromQL/MetricsQL 输入框。

## 目标

- 单指标策略行为与当前一致，保存结构和扫描语义保持稳定。
- 多指标策略通过多行指标输入和公式表达最终指标。
- 用户在页面中编辑 `a / b * 100` 这类公式，而不是编辑编译后的 MetricsQL。
- 多指标最终结果继续复用现有阈值、连续触发、恢复、无数据和通知链路。
- 条件维度从现有 AND 能力升级为 AND/OR，单指标和多指标都可使用。
- `${metric_name}` 在单指标取指标显示名，在多指标取公式结果名称。
- 公式结果无数据时触发无数据告警，不对子查询分别告警。

## 非目标

- 不迁移历史单指标策略。
- 不在普通策略页面新增 PromQL/MetricsQL 创建入口。
- 不开放完整 PromQL/MetricsQL 语法。
- 不在第一阶段支持多个表达式分别触发不同告警。
- 不在第一阶段支持跨数据源 join、同比环比、复杂条件表达式。

## 方案选择

采用“结构化指标输入 + 受限公式 + MetricsQL 编译器”方案。

不保存编译后的 MetricsQL。落库保存用户可编辑的公式和每行指标结构，扫描和预览时由后端编译为 MetricsQL。这样可以保留前端回填能力、做变量和维度校验、限制查询风险，并为后续函数扩展留出空间。

## 数据结构

`MonitorPolicy` 不新增数据库列，继续使用 `query_condition` JSON。现有类型保持不变：

- `metric`：旧单指标结构，继续用于历史策略和新建单指标策略。
- `pmq`：历史兼容和 Trap 场景，普通策略页不新增创建入口。
- `formula`：新增多指标结构。

示例：

```json
{
  "type": "formula",
  "result_name": "HTTP 5xx 错误率",
  "expression": "a / b * 100",
  "queries": [
    {
      "ref": "a",
      "metric_id": 101,
      "filter": [
        { "name": "service", "method": "=", "value": "checkout" },
        { "logic": "and", "name": "status", "method": "=~", "value": "5.." }
      ],
      "group_algorithm": "sum",
      "group_by": ["instance_id", "status"]
    },
    {
      "ref": "b",
      "metric_id": 102,
      "filter": [
        { "name": "service", "method": "=", "value": "checkout" }
      ],
      "group_algorithm": "sum",
      "group_by": ["instance_id"]
    }
  ]
}
```

兼容规则：

- 旧 `metric` 策略不迁移。
- 编辑旧 `metric` 策略时，前端回填为指标编辑器中的一行 `a`。
- 新建单指标策略仍保存为 `metric` 结构。
- 只有多指标策略保存为 `formula` 结构。
- `pmq` 继续兼容扫描和预览，但普通 metric 策略页面不开放原始查询创建。

## 前端交互

“定义指标”步骤升级为指标编辑器。

单指标状态：

- 默认只有一行变量 `a`。
- 不展示公式行。
- 条件维度、分组聚合方式、分组维度沿用现有控件。
- 保存时仍生成旧 `metric` payload。

多指标状态：

- 点击“添加指标”新增行，变量自动按顺序分配 `a`、`b`、`c`。
- 每行支持选择指标、条件维度、分组聚合方式、分组维度和删除。
- 多指标展示公式行：`结果名称 = 表达式`。
- 删除指标后，若表达式仍引用被删除变量，保存前提示。
- 右侧预览展示公式最终结果序列，标题取 `result_name`。

条件维度：

- 复用现有 `{name, method, value}` 结构。
- 新增可选 `logic`，从第二条条件开始生效。
- 缺省 `logic = and`，兼容旧数据。
- 条件语义为 OR 分隔 AND 组：`A AND B OR C AND D` 解释为 `(A AND B) OR (C AND D)`。
- 不支持括号和嵌套条件组。

## 表达式语言

第一阶段支持：

- 变量：`a`、`b`、`c` 等指标行变量。
- 数字：整数和小数。
- 运算符：`+`、`-`、`*`、`/`。
- 括号：`(`、`)`。

表达式中不能引用不存在的变量。变量名由前端自动分配，后端仍校验唯一性和引用合法性。

后端模块设计预留函数注册表，后续可扩展 `safe_div`、`default`、`clamp`、`abs`、`round` 等受控函数。第一阶段如未实现函数，校验阶段拒绝函数调用。

## 查询编译

新增表达式引擎模块，建议结构：

```text
server/apps/monitor/expression/
  ast.py
  parser.py
  validators.py
  compiler.py
  functions.py
  errors.py
```

职责：

- Parser：把用户公式解析成 AST。
- Validator：校验变量、函数、参数、维度、条件和注入风险。
- Compiler：把结构化指标输入和 AST 编译为 MetricsQL。
- Functions：函数注册表，定义函数签名和编译规则。
- Errors：表达式错误类型和用户可读消息。

指标输入编译复用现有 `Metric.query`、`format_to_vm_filter`、`group_algorithm` 和 `group_by` 逻辑，避免重复实现 label 拼接。

全 AND 条件继续编译为 label selector：

```promql
metric{service="checkout",status=~"5.."}
```

包含 OR 时编译为 selector 组合：

```promql
metric{service="checkout",status=~"5.."} or metric{service="checkout",status="499"}
```

## 维度匹配规则

多指标不要求所有行 `group_by` 完全相同，但必须保证公式结果有明确告警实例。

规则：

1. 公式中第一个出现的变量是结果锚点。
2. 最终公式结果维度、告警唯一性、`dimensions`、`metric_instance_id` 和 `${metric_xxx}` 维度变量跟随锚点指标的 `group_by`。
3. 非锚点指标的 `group_by` 必须是锚点 `group_by` 的子集，或与锚点完全相同。
4. 非锚点指标如果包含锚点没有的额外维度，保存和预览校验失败。
5. 非锚点指标是锚点维度子集时，编译器自动生成 `on(...) group_left`。
6. 非锚点子集不包含锚点主实例维度时允许，但返回 warning，提示该指标会跨缺失维度复用。

示例：

```text
a by(instance_id, config_type)
b by(instance_id)
公式：a / b
```

编译为：

```promql
(a_query) / on(instance_id) group_left (b_query)
```

场景表：

| 场景 | 处理 |
| --- | --- |
| `a(1,2) / b(1,2)` | 允许，直接计算 |
| `a(1,2) / b(1)` | 允许，生成 `on(1) group_left` |
| `a(1,2) / b(2)` | 允许并 warning，生成 `on(2) group_left` |
| `a(1,2) / b(1,4)` | 拦截，`b` 有锚点外额外维度 |
| `a(1,2) / b(3,4)` | 拦截，无法唯一匹配 |
| `a(1,2) / b(1) - c(2)` | 允许并 warning，结果仍按 `a(1,2)` 告警 |

该规则支持明细指标除以粗粒度总量，例如每个 `status`、`config_type` 或 `path` 的占比，同时避免 `path` 与 `method` 这类多对多误匹配。

## 评估流程

策略评估顺序保持：

```text
指标行生成基础序列
-> 多指标按公式计算最终序列
-> 策略级聚合周期和聚合方式评估
-> 阈值判断
```

`formula` 对下游表现为一个最终指标序列。阈值、连续触发、恢复、无数据、事件创建、告警创建和通知发送继续复用现有链路。

## 无数据与异常处理

- 公式最终结果无数据时，走现有无数据告警逻辑。
- 子查询单独无数据不直接触发无数据告警。
- 子查询有数据但公式结果为空时，预览返回提示：指标输入有数据，但公式结果为空，请检查分组维度和匹配关系。
- 查询失败不生成普通阈值告警。
- 编译失败或静态校验失败时策略不能保存。
- 普通 `/` 的除零行为按 MetricsQL 结果处理；预览可给出除零风险提示。后续可引导使用 `safe_div`。

## 模板变量

- 单指标：`${metric_name}` 取指标显示名。
- 多指标：`${metric_name}` 取 `result_name`。
- 多指标的 `${metric_xxx}` 维度变量来自公式最终结果序列标签，不能来自某个子查询的额外标签。

## API 与服务集成

现有策略创建和更新接口继续使用 `MonitorPolicySerializer`，但扩展 `query_condition` 校验。

预览继续复用当前策略预览入口，payload 与保存结构一致，避免预览和扫描语义分叉。

扫描集成点：

```python
if policy.query_condition.get("type") == "formula":
    query = FormulaQueryBuilder(policy).build()
else:
    query = existing_query_builder(policy)
```

表达式逻辑集中在新模块，现有 `metric` 和 `pmq` 路径尽量不改动。

## 校验规则

静态校验：

- `formula.queries.length >= 2`。
- `result_name` 必填。
- `expression` 必填。
- 变量引用必须存在。
- 每行必须有 `metric_id`、`group_algorithm`、`group_by`。
- 条件维度必须完整。
- 条件 `method` 只允许 `=`、`!=`、`=~`、`!~`。
- 条件 `logic` 只允许 `and`、`or`，缺省 `and`。
- label name 继续使用现有 Prometheus label 白名单。
- 非锚点 `group_by` 必须是锚点 `group_by` 子集或完全相同。

预览校验：

- 编译后的 MetricsQL 能成功查询。
- VM 返回语法错误、向量匹配错误、超时等错误时转成中文提示。
- 公式结果为空但子查询有数据时返回维度匹配提示。

## 测试范围

后端：

- 旧 `metric` 单指标策略保存、编辑、预览、扫描行为不变。
- 历史 `pmq` 策略扫描和预览兼容。
- 单指标条件支持 AND/OR，旧无 `logic` 条件仍按 AND。
- 多指标错误率 `a / b * 100` 可创建、预览和扫描。
- `result_name` 缺失不能保存。
- 表达式引用不存在变量不能保存。
- 删除被公式引用的变量不能保存。
- 非锚点维度是锚点子集时生成 `on(...) group_left`。
- 非锚点有锚点外额外维度时不能保存。
- `a(1,2) / b(1) - c(2)` 允许并返回 warning。
- 公式结果无数据触发无数据告警。
- `${metric_name}` 单指标和多指标取值正确。
- 表达式注入和 label 注入被拒绝。

前端：

- 单指标回填为一行且保存为旧结构。
- 添加、删除多指标行后变量正确分配。
- 多指标展示并校验 `result_name` 和 `expression`。
- 条件维度从第二条开始展示 AND/OR。
- 删除被公式引用的指标后展示错误。
- 预览成功、warning 和错误状态展示正确。

## 分期

第一阶段：

- 多指标结构化输入。
- 四则运算和括号。
- AND/OR 条件维度。
- 自动 MetricsQL 编译。
- `on(...) group_left` 维度匹配。
- 多指标预览、保存、扫描、阈值和无数据告警。

后续阶段：

- 函数注册表开放 `safe_div`、`default`、`clamp` 等函数。
- 时间窗口函数和偏移函数。
- 更高级的公式匹配设置。
- 条件表达式。

## 风险

- MetricsQL 向量匹配语义复杂，必须用预览和可读错误降低误配风险。
- 子查询有数据但公式结果为空容易误解，需要专门提示。
- 不同维度匹配可能放大序列数量，需要限制预览和扫描查询成本。
- 多指标公式的单位语义可能不再能从单个指标推导，第一阶段以 `calculation_unit` 或用户选择的结果单位为准。
