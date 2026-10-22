# Monitor 多指标条件告警策略

Status: implemented

需求来源：2026-10-20 产品讨论「监控告警策略支持多指标告警：满足指标 a 的同时也满足指标 b，涉及多阈值」。
竞品对照（腾讯云可观测「任意 / 所有 / 复合」、Azure Monitor 多条件 AND、Datadog Composite
`&&` 取最低级别、蓝鲸监控关联告警）与交互 Demo 见同日会话；本 spec 只覆盖 Monitor 策略，
APM / Log 不在范围。决策记忆见 `docs/design/product-decisions/monitor-policy-multi-metric.md`。

## Problem Statement

现场运维要表达「CPU 高 **且** 内存高才算故障」「错误率高 **且** 流量够大才报」「刚开机的主机不要报」。
现有策略只有三种出口：单指标、手写查询、计算指标（公式）。公式能把 a、b 算成一个数再比一组阈值，
但「a 和 b 各自过线」不是一个数能表达的，用户只能建两条策略各报各的，再靠人脑做「且」。
告警噪音来自这里：单条件各自触发，没有一个地方能说「两件事同时发生」。

多级别阈值让问题更难：致命 / 严重 / 预警三级，每级都要同时约束两个指标，没有一个简单的一致语义。

## Solution

策略新增第三种指标模式「多指标条件」：一条策略里列 2～5 个条件，每个条件是一个完整的
「指标 + 过滤 + 分组聚合 + 维度 + 汇聚方式 + 单位 + 自己的阈值阶梯」，组合方式为「全部满足」。

- **级别取最低**：每个条件按自己的阶梯命中一个级别，策略级别 = 各条件命中级别中最低的那个；任一条件
  一级都没命中则不触发。与 Datadog `&&` 规则一致，也等价于「按级别逐行配阈值」的矩阵在阶梯单调时的结果。
- **前置条件**：条件可标记为「前置条件」，只有一条阈值、没有级别，只做门槛，不参与级别合成。
- **维度对齐沿用公式规则**：第一个条件是锚点，其维度必须含实例身份；其余条件维度是锚点维度的子集，
  缺失的维度按锚点广播。
- 用户不写表达式；多指标模式下比较基准锁「当前值」，不开放恢复阈值（滞回）；汇聚周期、连续 N、
  恢复 N、无数据沿用策略级配置。
- 扫描、预览、试跑、快照、告警详情、策略组阈值编辑、模板全部认识这个新形态；试跑逐条件说明
  「哪个条件没过、为什么不触发」。

对外不说「对齐腾讯云 / Datadog」；表单里不出现 `AND` / `&&` / PromQL。

## User Stories

1. 作为现场运维，我想在一条策略里配「CPU 使用率 > 80% 且 内存使用率 > 85%」，让两件事同时发生才产生告警，而不是两条策略各报各的。
2. 作为现场运维，我想给每个条件分别配致命 / 严重 / 预警三级阈值，并且清楚知道「CPU 到致命、内存只到预警」时策略报的是预警，不必再猜。
3. 作为现场运维，我想加一条「系统运行时长 > 600 秒」或「请求数 > 100」作为前置条件，让刚开机 / 低流量实例不触发，但它不影响级别高低。
4. 作为现场运维，我想在保存前点「试跑」，逐实例、逐条件看到当前值、命中级别、哪个条件没过，知道这条策略现网会不会响。
5. 作为值班人员，我想在告警内容和告警详情里同时看到各条件的值和曲线，而不是只看到一个数。
6. 作为策略组管理员，我想在策略组里像改普通规则一样改多指标规则的阈值，每个条件各改各的。
7. 作为既有客户，我不改旧策略就保存，单指标、手写查询、公式策略的扫描结果与升级前完全一致。
8. 作为售前，我需要表单里不出现表达式框、不出现 `AND`，组合方式只有「全部满足」。

## Implementation Decisions

### D1. 数据形态：全部放在 `query_condition`，不加列

`MonitorPolicy.query_condition.type` 新增 `multi`。条件级字段全部收在 `queries[]` 内，不新增模型列。
形状（来自 Demo 原型，裁掉展示字段）：

```json
{
  "type": "multi",
  "result_name": "CPU 与内存双高",
  "combinator": "all",
  "queries": [
    {
      "ref": "a",
      "metric_id": 12,
      "filter": [],
      "group_algorithm": "avg",
      "group_by": ["instance_id"],
      "algorithm": "avg_over_time",
      "count_predicate": {},
      "metric_unit": "percent",
      "calculation_unit": "percent",
      "threshold_unit": "percent",
      "role": "level",
      "threshold": [
        {"level": "critical", "method": ">", "value": 90},
        {"level": "error", "method": ">", "value": 85},
        {"level": "warning", "method": ">", "value": 80}
      ]
    },
    {
      "ref": "c",
      "metric_id": 31,
      "filter": [],
      "group_algorithm": "max",
      "group_by": ["instance_id"],
      "algorithm": "last_over_time",
      "metric_unit": "s",
      "calculation_unit": "s",
      "threshold_unit": "s",
      "role": "gate",
      "threshold": [{"method": ">", "value": 600}]
    }
  ]
}
```

- `queries[0]` 是锚点；`ref` 沿用公式的 a / b / c 序列。
- `role ∈ {level, gate}`；`level` 的 `threshold` 是现有阶梯形状（`level` 去重），`gate` 的 `threshold` 恰好一条且不带 `level`。
- `combinator` 本期只接受 `all`；字段保留是为了试跑与表单显示，不是为 `any` 预埋实现。
- 策略级单值字段对 `multi` 的处理：`group_by`、`algorithm`、`group_algorithm`、`metric_unit`、`calculation_unit`、
  `threshold_unit` 由 serializer 从锚点条件镜像写入，满足既有必填与实例主键校验；`threshold` 写空列表；
  `compare_mode` 固定 `absolute`、`compare_value_kind` 为空、`recovery_threshold` 为空、`count_predicate` 为空。
  判定、编译、单位换算一律只读 `queries[]`，不读镜像字段。
- 模板 `config` 与 portable 导出 / 导入与公式同一套：每个条件的 `metric_id` 导出成 `metric_name`，导入时按插件解析回 id，解析不到则整条拒绝。

### D2. 校验：serializer 一次拒绝，复用公式校验器的维度规则

新增 multi 校验器，与公式校验器共享 `filter`、`group_by`、`metric_id`、`group_algorithm` 的单项校验，并追加：

| 规则 | 说明 |
|---|---|
| `2 ≤ len(queries) ≤ 5` | 上限对齐 Azure；超出拒绝 |
| `ref` 非空且唯一；`result_name` 必填 | 同公式 |
| 锚点 `group_by` 含 `instance_id`，并满足监控对象多键子身份要求 | 复用 `group_by` 既有校验（首位主键、多键对象子键齐全） |
| 非锚点 `group_by ⊆` 锚点 `group_by` | 同公式；维度不等时产出 `MULTI_DIMENSION_REUSE` 警告（文案同 `FORMULA_DIMENSION_REUSE`） |
| 至少一个 `role=level` 条件 | 全是前置条件没有级别可报 |
| `level` 条件：阈值 ≥ 1 条，`level` 合法且不重复，`method` 合法，`value` 有限数 | 同现有 `threshold` 校验 |
| `gate` 条件：阈值恰好 1 条且无 `level` | 门槛不参与级别 |
| 每条件 `algorithm` 在白名单内；`count_if_over_time` 必须带本条件 `count_predicate`；`rate` 且基础查询已含 `rate/irate/increase` 拒绝 | 同单指标禁则，逐条件应用 |
| 每条件 `threshold_unit` 与本条件结果单位可换算 | 同单指标，逐条件应用 |
| 枚举指标条件：不允许新算法；阈值运算符限枚举集 | 同单指标 |
| 策略级 `compare_mode ≠ absolute`、`recovery_threshold` 非空、`collect_type = trap`、`compare_mode = timeleft` | 多指标模式一律拒绝，不静默清空 |

逐序列算法（`rate` / `changes` / `deriv`）**允许**逐条件使用：公式禁它是因为比值的 rate 无意义，
多条件每个条件独立求值，不存在这个问题。

### D3. 查询：N 条编译，Python 侧按锚点维度 join，不引入新 MetricsQL 形态

- 每个条件构造一个「条件级 policy_like」（本条件的 `algorithm`、`group_algorithm`、`count_predicate`、
  `compare_mode=absolute`、`collect_type`、`query_condition={type: metric, metric_id, filter}`），
  走现有 `compile_window_query` / `compile_policy_query` / `compile_existence_query`。编译出的字符串形态与现网单指标完全相同，
  因此不需要再做 VictoriaMetrics 版本实跑确认。
- 比较查询：对每个条件各执行一次范围查询（同一 `period`、同一 `points`、同一右端点 `last_run_time`，
  实例范围按条件各自的基础查询注入 selector、沿用现有分批）。结果按 `ref` 收集。
- 单位换算：每个条件按自己的 `metric_unit → calculation_unit` 换算序列值，按自己的 `threshold_unit → calculation_unit`
  换算阈值副本。
- 存在性查询与基线：只对锚点条件执行；`PolicyInstanceBaseline` 继续以锚点维度元组为 `metric_instance_id`。
- 快照窗口查询（告警前一点、回填）：N 条，按 `ref` 收集。
- 性能边界：每轮扫描查询次数 = 条件数 × 实例批次数，条件数 ≤ 5；不额外加缓存。

### D4. 判定：join + 级别取最低，连续 N 逐级判

新增多条件判定，输入是 `{ref: 格式化后的序列表}`，输出仍是三类事件（`alert_events` / `info_events` / `hold_events`），
事件形状与现有 `calculate_alerts` 一致，下游事件入库、计数、恢复、快照不改。

- **行的身份**：以锚点维度元组为 `metric_instance_id`；非锚点条件把锚点元组投影到自己的 `group_by` 得到 join 键（广播语义同公式的 `group_left`）。
- **点的对齐**：所有条件同 `period` / `step` / 右端点，时间戳天然对齐；仍按时间戳取交集，交集不足 `trigger_count` 个点的行跳过（同现有「样本不足则跳过」）。
- **级别**：从高到低遍历级别 L；若所有 `level` 条件在最近 N 个点都满足各自的 L 阈值，且所有 `gate` 条件在最近 N 个点都通过，
  则在 L 触发并停止。无任何 L 成立则不触发。这与现有「`_all_meet_threshold` 逐级 break」是同一个算法推广到多条件；
  阶梯单调时等价于「各条件命中级别取最低」。
- **事件值**：`value` 取第一个 `level` 条件（通常是锚点）的最后一点换算后数值；`raw_data` 改为 `{"series": {ref: 原始序列项}}`，
  并带 `condition_values: {ref: 数值}`。
- **不触发的归类**：所有条件都有数据但组合不成立 → `info_events`（现有恢复计数照常累加，`recovery_condition` 个周期后恢复）。
  某个非锚点条件在该行缺数据 → 本轮不进任何一类：不触发、不恢复、`info_event_count` 不变（与计算方式丰富 spec 的「缺对照保持」同一语义）。
  已确认（2026-10-20）：缺数据不等于不满足，误恢复比多挂一轮更危险；悬挂风险由锚点条件自身的无数据告警兜底。不采用 Azure「任一条件不成立即恢复」。
- 滞回：多指标模式不支持 `recovery_threshold`，判定里不产生 `hold_events`（返回空列表以保持三元组签名）。

### D5. 无数据

- 无数据检测、无数据恢复只看锚点条件的存在性查询；非锚点条件不产生 `no_data` 告警。
- 非锚点条件缺数据对阈值路径的影响只有一个：该行本轮保持。试跑把它显式报出来（D6）。

### D6. 试跑与预览

- 试跑沿用现有端点与权限，payload 走同一 serializer。返回逐实例项追加：
  - `conditions: [{ref, metric_name, value, result_unit, hit_level | gate_passed, matched_threshold}]`
  - 新 verdict `missing_condition_data`（锚点有数据、某条件无数据），`reason` 写明是哪个 `ref`
  - `would_trigger` 的 `reason` 写「各条件级别不同，取最低」或「各条件级别一致」；`ok` 的 `reason` 写「前置条件 x 未通过」或「条件 x 未命中任何级别」
  - `trigger_count > 1` 时的「本轮命中 k/N」文案不变
- 预览：多指标模式下每个条件一条曲线，各带自己的阈值线与单位；用页签切换条件，不叠在一张图上（单位不同）。
- 试跑与预览都不新增日志等级 INFO 的 VM 响应输出；失败路径沿用现有单条 WARNING 模板。

### D7. 告警内容、告警中心、快照、告警详情

- `metric_name` / 告警中心 `item` = `result_name`。
- 模板变量：`${value}` 仍是第一个 `level` 条件的值并带单位；新增每个条件的 `${<ref>_value}`（带该条件单位）与 `${<ref>_metric_name}`。
  其余变量（资源、维度、父对象）不变。
- `MonitorAlert.value` / `MonitorEvent.value` 为第一个 `level` 条件的值（模型字段不改）。
- 快照点 `raw_data` 为 `{"series": {ref: …}}`，`current_value` 取第一个 `level` 条件，追加 `condition_values`；`result_unit` 为该条件的结果单位。
- 告警详情图：`raw_data.series` 存在时按条件分页签渲染，每页一条曲线、各自单位与阈值线；旧单序列快照渲染不变。

### D8. 策略组、模板、接入页

- 策略组「只改阈值」：规则更新接受 `condition_thresholds: {ref: threshold[]}`，服务端逐条件替换 `queries[*].threshold` 并走 D2 校验；
  按旧阈值正在告警的事件在改阈值后结束（沿用现有决策）。策略组页面对多指标规则按条件堆叠渲染阈值编辑器（复用现有阈值列表组件，每条件一组，前置条件一行）。
- 策略组规则的「有无对应指标」判断：多指标规则要求全部条件的指标都在当前插件下才算有数据，否则接入页标「这次没有数据」。
- 模板归一化 / 导出 / 导入见 D1；模板列表与详情显示 `result_name`。

### D9. 表单

- 「定义指标」顶部新增显式模式选择：单指标 / 计算指标 / 多指标条件。现有「按行数推断公式模式」改为显式状态，单指标与公式表单不变。
- 多指标模式：条件行复用公式的指标行（变量 / 指标 / 过滤 / 分组聚合 / 维度），每行追加「汇聚方式」「单位」与「角色」（常规 / 前置条件）；
  第一行标「锚点」；「添加条件」到 5 条置灰。
- 「告警条件」：组合方式只显示「全部满足」（任意 / 复合不出现在表单里，也不做置灰占位）；比较基准、恢复阈值在此模式下不显示；
  连续 N / 恢复 N / 无数据沿用策略级控件。阈值区按条件堆叠，每条件一组阶梯（复用现有阈值列表组件），前置条件单独一行单阈值。
  按级别矩阵视图不进 MVP。
- 阈值区底部实时复述一句人话：「当 CPU 使用率 > 80%（预警起）且 内存使用率 > 85%（预警起）且 系统运行时长 > 600s 时触发；级别取各条件命中级别的最低者」。
- 编辑回显：`type=multi` 时按 `queries[]` 还原行、角色、阶梯与单位。
- 编辑已有策略时允许切换模式；`query_condition.type` 变化时表单提示「保存后该策略下未恢复的告警会结束」，后端在保存事务内结束这些告警并发恢复 / 关闭通知（复用策略组改阈值结束旧告警的路径）。
- 保存 payload：按 D1 构造 `query_condition`，镜像字段由后端写入，前端不复制一份。
- 布局用 Tailwind `className`，沿用现有标签宽常量与 AntD 组件；不新增 SCSS Module，不硬编码色值。

## Testing Decisions

好的测试只锁外部行为：serializer 接受 / 拒绝、每个条件编译出的 MetricsQL 字符串、三类事件的划分与级别、试跑响应与零副作用、
快照与模板变量的渲染、策略组改阈值后的落库与告警结束。不测 join 的内部数据结构。

后端（沿用 `apps.monitor.tests` 既有 pytest 风格，sqlite 内存库，VM API monkeypatch）：

- 校验：D2 每条规则一个拒绝用例 + 一个合法接受用例；`queries` 为 1 条或 6 条拒绝；全 gate 拒绝；`compare_mode` 非 absolute 拒绝；trap 拒绝。
  先例：公式校验器测试、策略 serializer 校验测试。
- 编译：多指标策略每个条件编译出的字符串与同参数单指标策略逐字相同；存在性查询只对锚点。先例：策略查询编译测试、公式编译器测试。
- 判定：
  - 两条 level 条件 (致命, 预警) → 预警；(致命, 致命) → 致命；(致命, 未命中) → info；
  - gate 未通过 → info，不论 level 条件多高；
  - 非锚点维度子集广播：主机级内存 × 磁盘分区级使用率，按分区出事件、内存值复用；
  - `trigger_count = 2`：第一点双致命、第二点一致命一预警 → 预警；某点缺一个条件 → 跳过该行；
  - 非锚点缺数据 → 不进三类，活动告警 `info_event_count` 不变；
  - 事件 `value` 为第一个 level 条件，`raw_data.series` 含全部 ref。
  先例：阈值计算测试、告警检测器测试、公式扫描测试。
- 单位：条件 a 为 percent、条件 b 为 bytes→gibibytes 时各自换算，阈值副本各自换算，策略配置不被改写。先例：指标查询服务单位测试。
- 恢复与无数据：组合不成立连续 `recovery_condition` 轮后恢复；锚点无数据产生 `no_data` 事件、非锚点无数据不产生。先例：扫描器测试、基线服务测试。
- 试跑：`missing_condition_data`、gate 未通过、级别取最低三种 `reason`；`conditions` 逐条件字段齐全；调用后告警 / 事件 / 快照计数不变、通知与告警中心 mock 未被调用。先例：试跑服务测试。
- 快照与模板变量：`${value}` / `${a_value}` / `${b_metric_name}` 渲染；快照点含 `condition_values`；portable 导出每条件 `metric_name`、导入解析回 id、解析失败整条拒绝。先例：模板可移植测试、模板聚合测试。
- 策略组：`condition_thresholds` 落库到对应 `ref`；非法 ref 拒绝；改阈值后旧告警结束。先例：策略组服务测试。
- 旧策略回归：单指标、pmq、formula 固定 payload 的扫描事件与升级前逐点一致。
- 日志回归：多指标路径不新增任何等级的 VM 响应正文输出；如新增日志须按 §8 补模板与独立参数测试。

前端（沿用策略页 `__tests__` 与 `scripts/monitor-policy-formula-payload-test.ts` 风格）：

- 保存 payload：多指标 `query_condition` 形状、gate 单阈值、不带镜像字段；编辑回显行、角色、阶梯、单位。
- 模式选择显式化后单指标与公式 payload 不变。
- 校验：第 6 条禁加、全 gate 阻止保存、非锚点维度超集阻止保存并给出提示。
- 复述句、试跑表逐条件列与 `missing_condition_data` 文案、预览页签。
- 策略组阈值编辑器按条件堆叠并提交 `condition_thresholds`。
- `pnpm lint` 与相关 `pnpm test:*`；改布局后 `pnpm type-check`。

## Out of Scope

- 组合方式「任意满足」与复合表达式 `(1 AND 2) OR 3`；基于已有策略告警状态的复合策略（蓝鲸「关联告警」/ Datadog Composite 形态）。
- 条件级比较基准（同窗 / 环比 / 容量线）、条件级或策略级滞回、OR 下的级别合成。
- 按级别矩阵视图；专家布尔表达式入口。
- 非锚点条件的无数据告警。
- APM、Log 的多条件告警。
- 新模型列或迁移；OpenAPI 网关新增端点（策略不对外暴露）。
- 现网 `_log_alert_events` 把 VM 全量响应打 INFO 的清理（多指标路径绕开即可）。

## Further Notes

### 切片顺序

1. **后端契约与判定**：multi 校验器与 serializer 禁则、镜像字段写入、条件级编译与 N 条查询、join + 级别取最低判定、
   事件 `value` / `raw_data.series`、锚点存在性与基线、快照按 ref 记录、模板变量、告警中心 `item`。旧策略回归套件先跑绿再合。
2. **试跑与预览**：逐条件返回、`missing_condition_data`、三种 `reason`、预览按条件出图。
3. **策略表单**：显式模式选择、条件行、堆叠阶梯、前置条件、锁定项、复述句、payload 与回显、试跑表、预览页签。
4. **策略组、模板、告警详情**：`condition_thresholds`、策略组阈值编辑器、接入页覆盖判断、模板归一化与 portable、告警详情多页签曲线、i18n。

约束：切片 3 依赖切片 1 的 serializer 契约；切片 2 不得排到最后——多条件没有试跑不算可上生产；切片 4 的策略组部分不能缺，
否则策略组规则无法使用多指标。

### 主验收

- 旧策略不改保存，扫描、通知、快照与升级前逐点一致。
- CPU 93 / 内存 96 → 致命；CPU 92 / 内存 87.5 → 预警；CPU 95 / 内存 61 → 不触发（试跑写「条件 b 未命中任何级别」）。
- 两项都到严重但运行时长 240s → 不触发（试跑写「前置条件 c 未通过」）。
- 内存无数据、CPU 86 → 不触发不恢复，活动告警保持，试跑写 `missing_condition_data`。
- 每个条件编译出的查询与同参数单指标策略一字不差；查询次数 = 条件数 × 批次数。
- 告警内容 `${a_value}`、`${b_value}` 带各自单位；告警详情按条件分页签出曲线。
- 策略组里改条件 b 的阈值只影响该规则覆盖的成员，旧阈值下的告警结束。
- 表单无表达式框、无 `AND`、组合方式只显示「全部满足」；比较基准与恢复阈值在多指标模式下不出现。

### 已确认成立的现网事实

- 公式校验器已实现锚点含 `instance_id`、非锚点维度 ⊆ 锚点、`FORMULA_DIMENSION_REUSE` 警告，可直接复用。
- `calculate_alerts` 逐级 break 的语义推广到多条件后，与「各条件命中级别取最低」在阶梯单调时等价。
- 单指标编译入口已接受 policy_like 字典，条件级编译不需要改编译器。
- 实例范围 selector 注入与分批在查询服务里已有，按条件基础查询各注入即可。
- 策略组规则更新目前只接受 `threshold`，需要扩成按 ref 的阈值更新。

### 决策记录

- 走「条件列表 + 全部满足」而不是布尔表达式或复合策略：前者贴合「不写表达式」立场并复用公式行编辑器；
  后者需要先建子策略、多一层状态合成引擎，与「不新做检测引擎」冲突。
- 级别取最低：业界唯一有明确文档的多条件 × 多级别语义（Datadog `&&`），且与现有逐级判定算法同构。
- 前置条件单独角色而不是「阶梯每级填同一个值」：Datadog 官方用例「错误率高且流量够大」就是门槛语义，用阶梯表达会让级别合成被门槛污染。
- 条件级字段放 `query_condition` 内而不是新表：与公式的 `queries[]` 同构，模板、portable、策略组都已经按 JSON 处理。
- 多指标模式锁比较基准与滞回：先把「同时满足」做对，相对计算叠加后单位与对照缺失语义会成倍复杂。
- 非锚点条件缺数据时活动告警保持而不是恢复：对运维而言误恢复比悬挂更危险；与现有缺对照语义一致，不多出一条规则；悬挂由锚点无数据告警兜底。
- 多指标模式本期不开放比较基准与滞回（已确认 2026-10-20）：先把绝对阈值的「同时满足」做对；相对计算叠加后单位与对照缺失语义成倍复杂，后置另起 change。
- 已有策略允许在编辑时切换到多指标模式（已确认 2026-10-20）：`query_condition.type` 发生变化时，保存同时结束该策略下全部未恢复告警（走策略组改阈值结束旧告警的同一路径），因为锚点维度变化会改变告警身份键。
- 非锚点条件不产生无数据告警、阈值只做按条件堆叠、不随版本带内置多指标模板（已确认 2026-10-20，均为默认后置）。

### 完成证据

验证命令、基线失败和实现判断见 `specs/changes/monitor-policy-multi-metric/verification.md`。
