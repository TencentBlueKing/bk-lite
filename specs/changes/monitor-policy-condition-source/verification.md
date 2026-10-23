# 监控策略定义指标两层化验证记录

后端 Django 测试走本机 Postgres（`pytest.ini` 的 `env_files=.env`），并保留 `--reuse-db`。没有改用 sqlite，因此没有碰到 `NewSessionEventRelation has no field named 'event'` 这条迁移基线失败。

## 切片 1 前端重排

完成。多条件卡内当时不渲染「计算」开关。三种旧载荷（单指标、计算指标、多指标条件）的派生类型与往返断言在载荷脚本里保持通过。

命令（`web/`）：

```bash
pnpm test:monitor-policy-formula-payload
pnpm exec eslint --fix \
  "src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx" \
  "src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx" \
  "src/app/monitor/(pages)/event/strategy/detail/metricConditionCard.tsx" \
  "src/app/monitor/(pages)/event/strategy/detail/metricOperandRow.tsx" \
  "src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts" \
  "src/app/monitor/(pages)/event/strategy/detail/page.tsx" \
  "src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx"
pnpm exec vitest run src/app/monitor/hooks/__tests__/issue5892LocaleKeys.test.ts
pnpm type-check
```

结果：载荷脚本通过；eslint 修完缩进后退出码 0；locale 键测试 1 个文件、2 条通过；`pnpm type-check` 退出码 0（Node 22 相对 engines 24 只有警告）。

浏览器（`http://localhost:3000`，已登录，监控对象 Host id 25，新建页）：

- 单条件·原生：第一层「单条件」，说明「一个指标或一个算出来的数，用一组阈值判断。」，来源「原生指标 / 计算指标」，一行 `a`，维度 `instance_id`，有「添加筛选」。没有「锚点」。
- 单条件·计算：维度选择在卡上只出现一次；操作数行没有自己的维度选择；卡内有「添加指标」和 `fx` 结果行。
- 多条件·原生：没有计算开关；说明「其余条件按第一条的实例对齐」；`a` / `b` 各有角色、汇聚、单位；底部「添加条件」。编辑器里没有 PromQL。

未覆盖：没有保存、没有预检；当时打开的已有策略是原生指标，没有回显一条已保存的计算指标策略。告警详情快照脚本在切片 1 没有改详情页，当时没跑。

## 切片 2 后端条件内公式

完成。旧 `metric` / `pmq` / `formula` / `multi` 先例与新的计算条件用例一起通过。

命令（`server/`）：

```bash
uv run pytest \
  apps/monitor/tests/test_policy_calculate_multi.py \
  apps/monitor/tests/test_formula_validator.py \
  apps/monitor/tests/test_formula_compiler.py \
  apps/monitor/tests/test_formula_policy_scan.py \
  apps/monitor/tests/test_policy_template_portability.py \
  apps/monitor/tests/test_monitor_policy_view_helpers.py \
  apps/monitor/tests/test_multi_validator.py \
  apps/monitor/tests/test_policy_multi_compile.py \
  apps/monitor/tests/test_policy_multi_scan.py \
  apps/monitor/tests/test_policy_multi_dry_run.py \
  apps/monitor/tests/test_policy_multi_preview.py \
  apps/monitor/tests/test_policy_multi_group.py \
  apps/monitor/tests/test_monitor_policy_serializer_multi.py \
  --no-cov -q --override-ini='addopts=-q --reuse-db'
```

结果：152 passed。覆盖：计算条件接受与形状拒绝、操作数 ref 跨条件重复、`count_if`、不带 `source` 的旧载荷、查询字符串与同参数公式策略逐字相同且每个操作数注入 `instance_id=~"h1"`、`count_if` 的 `bool` 与存在性 `last_over_time`、错误率 12 且请求数 300 判定为 error 且内容为「错误率 12.00%」、错误率缺数不触发不恢复、缺操作数指标整条失败、试跑带 `metric_name` / `expression` 且请求数 50 时原因是「前置条件 b 未通过」、模板操作数往返且结果名称不被当成目录指标、未知操作数拒绝整条模板、策略组阈值落库且接入页指标名含操作数不含「错误率」、预览卡片标题为结果名称、VM 响应正文不进日志。

基线失败：本轮没有。未使用 sqlite。

未覆盖：没有对真实 VictoriaMetrics 做一次在线扫描；扫描与预览都是 mock。

## 切片 3 放开多条件卡内「计算」

完成。

命令（`web/`）：

```bash
pnpm test:monitor-policy-formula-payload
pnpm test:monitor-alert-detail-snapshot
pnpm exec eslint \
  "src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts" \
  "src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx" \
  "src/app/monitor/(pages)/event/strategy/detail/page.tsx" \
  "src/app/monitor/(pages)/event/alert/information.tsx"
pnpm type-check
```

结果：两个脚本通过；eslint 退出码 0；`pnpm type-check` 退出码 0（同样只有 Node 22 引擎警告）。载荷脚本锁定：多条件计算条目含 `source`、`expression`、`operands`，条件 `group_by` 写进每个操作数，原生条目不带 `source`，多条件内切换来源不改变派生类型因此不提示，逐序列算法拒绝，回显 `source: formula`。告警详情页签标题「a 错误率」。

浏览器（同一新建页，未保存）：

- 切到多条件后，两张条件卡都有「原生指标 / 计算指标」。没有「锚点」，没有 PromQL，没有「未恢复告警将结束」弹窗（这条策略还没保存）。
- 第一条切到计算指标后：维度 `instance_id` 在卡上出现一次；操作数 `a1` / `a2` 只有指标、分组聚合和「添加筛选」，没有自己的维度选择；卡内有「添加指标」和 `fx` 结果行。第二条仍是原生指标。
- 页面上出现一条与本次无关的「验证身份」密码框，没有输入密码，因此没有继续预检、保存，也没有打开一条真实告警核对详情页签。

未覆盖：已保存策略上「多条件内切换来源不提示」只由载荷脚本锁定，浏览器没在已保存策略上点这一下；预检弹窗和告警详情页签没有用真实数据走查。

## 切片 4 多条件卡内阈值

当时未开始。2026-10-21 方案改成按级别分行，验证记在文末「阈值按级别分行」。

## 判断

- 筛选条件上的 AND/OR 保留。规格里的「无 AND」指多条件组合，组合文案仍是「全部满足」。
- SNMP Trap 的 PromQL 输入保留，它不是这两层指标表单。
- 计算条件的存在性查询与同参数公式策略一致：`avg_over_time` 仍走窗口聚合；`count_if_over_time` 才进入公式的 `last_over_time` 分支。没有把所有计算条件的存在性查询改成 `last_over_time`，否则会和「与公式策略逐字相同」冲突。
- 保存时若对象身份键被补进第一条的 `group_by`（例如 `container_id`），计算条件的操作数 `group_by` 一并写成同一份，避免操作数和条件维度脱节。
- 试跑 `conditions[]` 只在 `source: formula` 时增加 `expression`。旧原生条件不带这个键。
- 计算条件的结果名称不参与模板 `metric_id` 解析，也不打 `metric_plugin`。只解析操作数。

## 本地走查（2026-10-21）

库里没有 `formula` / `multi` 策略（35 条 `metric`、1 条 `pmq`），所以回显、预检落库、策略组改阈值、告警详情页签没有真实数据可点。走查用已保存的单指标策略 `id=1`（名称「测试计算指标」，类型实际是 `metric`）在编辑页切换，没有点保存。

通过：

- 回显为「单条件 · 原生指标」，指标 CPU使用率，比较基准和恢复阈值还在。没有「锚点」，没有 PromQL。
- 切到「计算指标」「多条件」时 `message.warning` 被调用（开发态 Next 把 antd 的静态 `message` 警告收成了错误浮层）。
- 多条件说明是「全部满足」，第一张卡写「其余条件按第一条的实例对齐」，比较基准和恢复阈值收起。
- 多条件里把第一条切成计算：维度 `instance_id` 只在卡上出现一次，操作数是 `a1` / `a2`，表达式 `a1 / a2 * 100`，操作数行没有维度选择。预检前的校验能指出缺结果名称、缺 `a2`、缺阈值。

漏洞：

- 单条件从原生切到计算，不会补第二行操作数，表达式仍是默认的 `a / b * 100`。预览直接报「表达式引用了不存在的变量：b」，复述句还停在「CPU使用率的平均 > 0 %」。
- 多条件复述句在阈值还没填数字时写成「当 cpu_usage_total （起）且 b （起）」。`lowestLevelThreshold` 丢掉 `value: null` 的阶梯后，级别变成空字符串，再拼成「起」。计算条件没填结果名称时，名字退回 `a`。
- 多条件编辑器底部另有一个策略级「结果名称」（后端 `result_name`，给 `${metric_name}` 用），和条件卡里的结果名称共用同一个占位符，两个字段挨在一起。
- 通知变量表没有 `${a_value}` / `${a_metric_name}`，只能手打。

## 走查问题修复（2026-10-21）

- 单条件切到计算时补第二行操作数，表达式仍是 `a / b * 100`。复述句改用结果名称。
- 多条件复述句在阈值没填数字时写「未设阈值」，不再拼出「（起）」。计算条件没填结果名称时，用操作数指标名，再没有就写「未命名结果」。
- 多条件底部的策略级名称改成「告警指标名」，占位符是「告警内容里的指标名」。多条件的变量表增加 `${ref_value}` 和 `${ref_metric_name}`。

`pnpm test:monitor-policy-formula-payload` 通过。编辑页刷新后没有保存：切到计算后是 `a` CPU 使用率加空的 `b`，预览是「指标 b 必须选择有效指标」，复述句是「计算指标的平均 > 0 %」；再切多条件，复述句是「当 cpu_usage_total 未设阈值且 b 未设阈值…」，变量表有 `${a_value}`。

## 生产走查（2026-10-21）

对象 Host（监控对象 25），采集模板「主机（Telegraf）」，实例 fusion-collector。新建页入口 `type=add`。用户正在改的策略 `id=1` 没有保存、覆盖或删除。没有出现可交互的「验证身份」密码框。切片 4（阈值进条件卡）、集合对齐入口、策略组里改维度或表达式，页面上都没有，按「看到不存在即通过」记。

### 自动门禁

通过，不构成阻塞。

- `pnpm test:monitor-policy-formula-payload`：`monitor-policy-formula-payload-test passed`。
- `pnpm test:monitor-alert-detail-snapshot`：`monitor-alert-detail snapshot validation passed`。走查结束前为混合页签补了一条断言后重跑，仍然通过。
- server pytest 七个文件：50 passed。

### 1. walkthrough-单原生

做了什么：新建单条件原生。CPU 使用率，平均值 by `instance_id`。空表预检前拦截。预览当前值约 49%，阈值放在两侧：严重 80、错误 60、警告 30。预检后保存，再打开。

实际结果：空表拦住，文案是「指标 a 必须选择有效指标」「资产不能为空」「请至少填写一个告警级别的阈值」。比较基准、恢复阈值都在。没有表达式，没有 a/b 操作数，没有 PromQL，没有「锚点」。预览有曲线。预检「会触发」，级别警告，当前值 56.9% > 30%。保存 `type=metric`。再打开仍是单条件原生，CPU 使用率，平均值 by `instance_id`，阈值 80/60/30，复述句「CPU使用率的平均 > 80 %」。

通过。未 mock。证据：策略 id 174。预检原文：`会触发 … 警告 56.9 % > 30.0 %`。

### 2. walkthrough-单计算

做了什么：单条件计算。a、b 都是 CPU 使用率，a 平均值、b 最大值，表达式 `a / b * 100`，结果名称「计算指标」，单位 percent。先清空结果名称再预检。预览当前值 100，阈值严重 110、错误 100、警告 90。

实际结果：缺结果名称时预检前报「结果名称不能为空」，没有发出预检请求。维度在每一行「by」旁边，不在卡片顶部。预览一条曲线，标题「计算指标（%）」，没有页签。复述句「这条策略在判断：计算指标的平均 > 110 %」。比较基准和恢复阈值还在。预检「会触发」，警告，100% > 90%。保存 `type=formula`。再打开表达式、聚合、维度、阈值与保存前一致。

通过。未 mock。证据：策略 id 175。载荷 `result_name=计算指标`，`expression=a / b * 100`，a `avg` / b `max`，`group_by=[instance_id]`。预检原文：`会触发 … 警告 100.0 % > 90.0 %`。

### 3. walkthrough-多原生

做了什么：两条原生。a CPU 等待 IO 占比，b CPU 单核使用率，角色都是常规。预览 a 当前约 7.7%，b 约 96%。a 阈值 20/12/3，b 阈值 120/110/50。

实际结果：缺指标、缺阈值时预检前点名「指标 a」「指标 b」「条件 a 至少需要一条阈值」「条件 b 至少需要一条阈值」。说明是「其余条件按第一条的实例对齐」。第一张卡没有「锚点」控件。比较基准和恢复阈值不在表单里。复述句含「且」和「级别取各条件命中级别的最低者」。预览页签是 a、b，点 b 后标题变成 CPU Core Usage。预检「会触发」，警告。保存 `type=multi`，两条 `source` 为 null，没有表达式。再打开指标、维度 `instance_id`、角色常规、阈值与保存前一致。

选 b 时维度下拉自动带上 `cpu`，预览报「条件 b 包含锚点外额外维度：cpu」。手删 `cpu` 后才能继续。这是缺陷，本条在删掉之后通过。

通过（带上述缺陷）。未 mock。证据：策略 id 176。预检原文：`会触发 a CPU IOWait Rate 7.857… warning；b CPU Core Usage 96.888… warning … 警告 7.9 % > 3.0 % 各条件级别一致`。

### 4. walkthrough-多计算

做了什么：两条都切成计算。a 是 `a1 / a2 * 100`，结果名「使用率比」（CPU 使用率平均 / 最大）。b 是 `b1 / b2 * 100`，结果名「等待比」（CPU 等待 IO / CPU 单核）。维度在操作数行。浏览器里把表单填到预检前。

实际结果：缺结果名称、缺指标、缺阈值时，预检前能点名条件 a/b 和操作数 a1/a2、b1/b2。填完之后，预览和预检都被前端校验挡住，原文只有「至少需要配置一个指标」。两条都是 `source=formula` 时，`validateMultiConditionRows` 把非计算行滤成空数组，再走「至少需要配置一个指标」。已保存的策略重新打开，预览仍是这句。页签因此没有点到，看不到「点页签后名称和曲线一起变」。

绕过页面，用同一套载荷调预检和创建接口。预检 `would_trigger`：a「使用率比」100 warning，b「等待比」10.19 warning，原因「各条件级别一致」。创建成功。再打开：两条都是计算，表达式、操作数、维度 `instance_id`、阈值与载荷一致。

失败。预检和落库是 mock（浏览器校验挡住后改走策略 API）。证据：策略 id 177。失败原文：`至少需要配置一个指标`。API 预检原文：`would_trigger`，a 100 > 90 warning，b 10.187 > 4 warning。

### 5. walkthrough-混合

做了什么：a 计算，结果名「使用率比」，`a1 / a2 * 100`，常规，三级阈值 130/110/90。b 原生 CPU 使用率，前置条件，一条不带级别的阈值。先把 b 设为 50（当前值过得去），再改成 120（过不去）。

实际结果：缺项时预检前点名「条件 a 必须填写结果名称」「指标 a1/a2」「指标 b」「条件 a/b 至少需要一条阈值」。预览有页签 a、b，曲线和 130/110/90 标线都在。两拍都是真实序列：

- b > 50：会触发。a「使用率比」100 warning，b CPU Usage 94.97 pass。级别警告，来自 a。原因「各条件级别一致」。
- b > 120：不触发。a 仍是 100 warning，b 95.62 fail。原因「前置条件 b 未通过」。

保存 `a.source=formula`，b 没有 source，`b.role=gate`，b 阈值 `[{method:>, value:120}]`。再打开模式、指标、表达式、维度、角色、阈值与保存前一致。没有 PromQL，第一张卡没有「锚点」。

点预览页签时页面一度变成「This page couldn’t load」。刷新后没有再点页签，预检两拍是在刷新后的表单上完成的。

通过。未 mock。证据：策略 id 178。预检原文见上。

### 横切 1 切换提示

做了什么：打开 id 174，从单条件原生改成多条件。打开 id 178，只把 b 从原生改成计算。都没有保存。

实际结果：174 切到多条件时，页面插入了「保存后该策略下未恢复的告警会结束」。开发态里这条 antd message 随即被拆掉，停不到一秒，所以肉眼容易错过，变更监听抓到了原文。178 只改一条的来源，页面没有这句，b 变成 `b1` 计算行。

通过。未 mock。证据：174 的插入原文；178 切换后 DOM 不含「未恢复」。

### 横切 2 维度

做了什么：单条件计算，a、b 都用 CPU 单核使用率。a 的分组是 `instance_id` + `cpu`，b 只留 `instance_id`。这条是 API 写入后再打开，不是在新建页手点出来的。b 的维度下拉在回显页打开。另交一条 b 比 a 多 `cpu` 的载荷。

实际结果：id 179 预检 `would_trigger`，当前值 99.59。再打开 a 是 `instance_id+cpu`，b 仍是 `instance_id`。b 的下拉只有 `instance_id` 和 `cpu`，选不出锚点外的维度。非法载荷被拒，没有落库。

通过。子集策略和拒绝是 API；下拉限制是浏览器回显。证据：策略 id 179。拒绝原文：`query_condition:指标 b 包含锚点外额外维度：cpu`（HTTP 400）。

### 横切 3 策略组只改阈值

做了什么：打开策略组页 `?objId=25`。没有把 walkthrough 策略挂进组，也没有在组里改阈值。对已保存的混合策略 178 在内存里调用 `PolicyGroupService._replace_condition_thresholds`，改 a、b 的阈值后不 `save`。已有 `test_policy_multi_group.py` 在门禁里通过。

实际结果：策略组列表没有「单条件 / 多条件」开关，页面源码里也没有这两词。内存替换后 a 阈值变为 11/9/7，b 变为 `> 3`，表达式、操作数 `group_by`、`source` 与替换前相同。刷新数据库，178 的阈值没变。

通过。浏览器没挂上组；阈值替换是服务调用，未写库。证据：178 内存替换结果 `expr_same/a_groupby_same/b_groupby_same/source_same/db_unchanged` 均为 true。

### 告警详情

混合策略预检会触发，本轮没有等扫描产出真实告警。页签标题走 `alertConditionTabLabel(ref, metric_name)`，已有断言是 `a 错误率`。快照脚本补了混合载荷：`a` 结果名「使用率比」、`b` 为 `cpu_usage_total`，断言页签为「a 使用率比」和「b cpu_usage_total」。`pnpm test:monitor-alert-detail-snapshot` 通过。没有真实告警。

### 能否上生产

不能上生产。

阻塞：

- 两条都是计算指标时，预览和预检被「至少需要配置一个指标」挡住。后端同一载荷可以预检并保存。策略 id 177。
- 多条件里选择带额外标签的原生指标（CPU 单核使用率）会自动把 `cpu` 放进分组，锚点没有这个维度时直接报「锚点外额外维度」。策略 176 是手删之后才保存的。

其余记录，不单独挡发布：新建页在指标目录加载完成时会把已经选好的多条件重置回单条件原生，等加载完再切可以绕过。切换类型的提示文案会插入 DOM，开发态停留时间极短。

## 生产阻塞修复（2026-10-21）

上面两条阻塞已修，并在本机策略页核对，没有保存。

- 策略 177：两条都是计算指标时，预览不再出现「至少需要配置一个指标」。点页签 b 后，阈值从 a 的 130/110/90 换成 b 的 40/20/4。
- 策略 176：条件 b 从「CPU单核使用率」换成「CPU使用率」再换回来，维度标签仍只有 `instance_id`，没有 `cpu`，也没有「锚点外额外维度」。

这两条不再挡发布。目录加载重置和开发态提示停留时间仍按上面的记录，不单独挡发布。

## 阈值按级别分行（2026-10-21）

多条件第三步「告警阈值」改成一张卡：一行一个级别，行内按全部常规条件填比较符和阈值，整行添加或删除。前置条件在分隔线下单独一段。单条件仍是原来的 ThresholdList。保存载荷、复述句、后端没有改。比较符外层包了 `w-[88px]`，因为表单里的 Select 会被拉成 100% 宽，数字框会被挤没。

### 命令

`cd web && pnpm test:monitor-policy-formula-payload`

```
[WARN] Unsupported engine: wanted: {"node":"24.x"} (current: {"node":"v22.16.0","pnpm":"11.20.0"})
$ pnpm exec tsx scripts/monitor-policy-formula-payload-test.ts
monitor-policy-formula-payload-test passed
```

通过。退出码 0。

`cd web && pnpm exec eslint` 覆盖 `formulaExpressionUtils.ts`、`multiThresholdGrid.tsx`、`alertConditionsForm.tsx`、`policy-group/page.tsx`、`multi-threshold-grid.stories.tsx`、`.storybook/preview.tsx`。无输出，退出码 0。通过。载荷脚本在 eslint ignore 里，没有纳入这次检查。

`cd web && pnpm type-check`

```
[WARN] Unsupported engine: wanted: {"node":"24.x"} (current: {"node":"v22.16.0","pnpm":"11.20.0"})
$ pnpm prepare-enterprise && next typegen && node scripts/sync-next-build-types.mjs && tsc -p tsconfig.build.json --noEmit
[WARN] Unsupported engine: wanted: {"node":"24.x"} (current: {"node":"v22.16.0","pnpm":"11.20.0"})
$ node scripts/prepare-enterprise.mjs
  ✓ ai-pilots: 21 file(s) (unchanged)
  📄 Dashboard metadata: src/app/monitor/dashboards/objects/(enterprise)-metadata.ts
  📄 Dashboard loaders: src/app/monitor/dashboards/objects/(enterprise)-loaders.ts
ℹ️ No web/enterprise link found, skipping enterprise preparation.
Generating route types...
✓ Types generated successfully
```

通过。退出码 0。Node 22 相对 engines 24 只有警告。`next typegen` 会改 `web/next-env.d.ts`，已把该文件恢复成检查前的既有脏内容。

没有跑 Storybook dev。

### 浏览器

`http://localhost:3000`，已登录。没有点保存或确认，没有打开策略 id=1。

- id=176（两条原生）：图例「a CPU等待IO占比 · b CPU单核使用率」。三行严重 / 错误 / 警告，每行 a、b 两格，比较符 `>`，数值 20/120、12/110、3/50，单位 %。圆点是红、橙、黄，没有左侧通高色条。列宽不够时 b 折到下一行。把警告行的 a 从 3 改成 9 后，复述句变成「CPU等待IO占比 > 9%（警告起）且 CPU单核使用率 > 50%（警告起）」，b 和其他格子不变。刷新后删掉错误行，只剩严重 20/120 和警告 3/50，复述句仍是警告起。再点「添加级别」，错误行插回严重和警告之间，a、b 都是空值，警告的 3 和 50 还在。没有保存。
- id=177（两条计算指标）：图例「a 使用率比 · b 等待比」。数值 130/40、110/20、90/4。复述句是「使用率比 > 90%（警告起）且 等待比 > 4%（警告起）」。
- id=178（a 计算 + b 前置条件）：级别行只有 a，130 / 110 / 90。分隔线下是「前置条件」，b 为 `> 120` %。复述句含「CPU使用率 > 120」。没有左侧色条。
- id=174（单条件原生）、id=175（单条件计算）：仍是 ThresholdList，有单位选择、「当结果是」和左侧色条。174 的数值是 80 / 60 / 30，175 是 110 / 100 / 90。没有多条件表格。
- 策略组 `?objId=25`：打开「Host默认告警」的规则，共 23 条，三页的 `query_type` 都是 `metric`。未找到多条件规则，未验证改阈值弹窗。没有点修改，没有点确认。
