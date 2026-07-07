# 监控告警策略多指标公式测试方案

## 测试目标

验证 Monitor 告警策略指标定义升级为“指标表达式编辑器”后，单指标旧逻辑不回归，多指标公式可创建、编辑、预览、保存和扫描，并覆盖单指标与多指标互相切换、历史策略兼容、非法输入防护、公式扫描语义等关键场景。

## 测试范围总览

| 模块 | 测试重点 | 通过标准 |
| --- | --- | --- |
| 单指标策略 | 新建、编辑、保存、预览、扫描 | 行为与旧版本一致，保存结构仍为 `metric` |
| 多指标公式 | 多行指标、结果名称、表达式、维度对齐 | 保存结构为 `formula`，预览和扫描使用最终公式结果 |
| 单/多切换 | 单指标加指标、删回单指标、反复切换 | 1 行自动为 `metric`，多行自动为 `formula` |
| 历史兼容 | 历史单指标、历史 `pmq`、历史 filter | 打开后不修改也能保存，不产生兼容回归 |
| 安全边界 | filter、group_by、metric_id、表达式变量 | 非法输入在前端或 API 边界拒绝，不能落库后扫描失败 |
| 扫描语义 | 阈值、无数据、除零、实例归属 | 只对公式最终结果告警，`inf/nan` 不误报 |

## 场景测试用例

| ID | 场景 | 前置条件 | 操作步骤 | 期望结果 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| S-01 | 新建单指标策略 | 有可选指标 | 选择 1 个指标，配置 `service = checkout`，保存 | 保存成功，`query_condition.type = metric` | P0 |
| S-02 | 单指标多个条件 | 有可选指标 | 配置 `service = checkout AND status =~ 5..`，保存 | 保存成功，filter 保留多个条件 | P0 |
| S-03 | 单指标 OR 条件 | 有可选指标 | 配置 `service = checkout OR status =~ 5..`，保存并预览 | 保存成功，查询语义为 OR | P0 |
| S-04 | 历史单指标无 logic filter | 存在旧策略，第二个 filter 无 `logic` | 打开编辑页后不修改，直接保存 | 不报“缺少 AND/OR 关系”，保存成功 | P0 |
| S-05 | 单指标模板变量 | 单指标策略触发告警 | 告警模板使用 `${metric_name}` | 渲染为指标名 | P1 |
| S-06 | 单指标转多指标 | 已有单指标编辑页 | 点击添加指标，增加 b 行 | 页面进入公式模式，展示结果名称和表达式 | P0 |
| S-07 | 多指标转单指标 | 已有 a、b 两行 | 删除 b，只剩 a | 页面回到单指标模式，保存走 `metric` | P0 |
| S-08 | 单/多反复切换 | 已有单指标编辑页 | a -> 加 b -> 删 b -> 加 b -> 删 b | 模式始终与行数一致，保存/预览不卡死 | P0 |
| S-09 | 创建 HTTP 5xx 错误率 | 有 5xx 和 total 指标 | 配置 `HTTP 5xx 错误率 = a / b * 100` | 保存成功，`query_condition.type = formula` | P0 |
| S-10 | 多指标结果名称缺失 | 多指标模式 | 清空结果名称后保存 | 保存失败，提示结果名称必填 | P0 |
| S-11 | 多指标表达式缺失 | 多指标模式 | 清空表达式后保存 | 保存失败，提示表达式必填 | P0 |
| S-12 | 表达式引用不存在变量 | a、b 两行 | 输入 `a / c` | 保存失败，提示变量 c 不存在 | P0 |
| S-13 | 删除被公式引用的指标 | a、b 两行，表达式 `a / b` | 删除 b 后保存 | 应回到单指标模式；若仍公式保存则必须提示 b 不存在 | P0 |
| S-14 | 表达式只引用单变量 | a、b 两行 | 输入 `a * 100` | 保存失败，提示至少引用两个不同变量 | P1 |
| S-15 | 表达式首变量不是首行指标 | a、b 两行 | 输入 `b / a` | 保存成功；公式 anchor 仍为首行指标 a，最终 group_by/告警归属不受表达式变量顺序影响 | P0 |
| S-16 | 锚点缺 instance_id | a group_by 为 `status` | 保存公式 | 保存失败，提示锚点 group_by 必须包含 `instance_id` | P0 |
| S-17 | 支持子集维度对齐 | a by `instance_id,status`，b by `instance_id` | 输入 `a / b` 保存 | 保存成功，生成 group_left/on 对齐查询 | P0 |
| S-18 | 拒绝额外非锚点维度 | a by `instance_id,path`，b by `instance_id,method` | 输入 `a / b` 保存 | 保存失败，提示非锚点包含额外维度 | P0 |
| S-19 | 三指标公式 | a by `instance_id,status`，b by `instance_id`，c by `status` | 输入 `a / b - c` | 按设计通过或给出复用 warning，预览正常 | P1 |
| S-20 | 多指标 metric_name | 多指标策略触发告警 | 告警模板使用 `${metric_name}` | 渲染为结果名称 | P0 |

## 边界与安全测试

| ID | 测试点 | 输入示例 | 入口 | 期望结果 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| B-01 | filter name 非法 | `bad label` | 前端/API | 拒绝保存 | P0 |
| B-02 | filter name 注入字符 | `bad"label` | 前端/API | 拒绝保存 | P0 |
| B-03 | filter method 非法 | `LIKE` | 前端/API | 拒绝保存 | P0 |
| B-04 | filter value 数组 | `["checkout"]` | 单指标/API | 拒绝保存 | P0 |
| B-05 | filter value 数组 | `["checkout"]` | 多指标/API | 拒绝保存 | P0 |
| B-06 | filter value 空字符串 | `""` | 单指标/多指标 | 允许保存 | P1 |
| B-07 | group_by 注入 | `x) or vector(1` | 单指标/API | 拒绝保存 | P0 |
| B-08 | formula group_by 注入 | `x) or vector(1` | 多指标/API | 拒绝保存 | P0 |
| B-09 | metric_id 不存在 | `999999` | 多指标/API | 保存失败，不能落库后扫描才失败 | P0 |
| B-10 | metric_id 非整数 | `abc`、`true`、`0` | 多指标/API | 保存失败 | P0 |
| B-11 | 一元负号限制 | `-a`、`a * -1` | 多指标 | 当前阶段可拒绝，但前后端提示一致 | P2 |
| B-12 | 表达式括号不匹配 | `(a / b` | 多指标 | 保存失败，提示括号不匹配 | P1 |

## 扫描与告警语义测试

| ID | 场景 | 构造数据 | 期望结果 | 优先级 |
| --- | --- | --- | --- | --- |
| E-01 | 公式结果超过阈值 | a/b*100 > 阈值 | 产生一条基于最终公式结果的告警 | P0 |
| E-02 | 子查询有数据但公式无结果 | a、b 维度无法匹配 | 不对子查询分别告警，按最终结果无数据处理 | P0 |
| E-03 | 公式结果无数据 | VM 返回空 result | 触发最终结果无数据告警 | P0 |
| E-04 | 除零产生 `+Inf` | b = 0 | 不触发阈值告警，不产生错误恢复 | P0 |
| E-05 | 公式结果为 `NaN` | 0 / 0 | 不触发阈值告警，不产生错误恢复 | P0 |
| E-06 | 聚合结果为 `inf/-inf/nan` | VM 返回非有限值 | 聚合格式化跳过该样本 | P0 |
| E-07 | 实例归属 | group_by 顺序为 `status,instance_id` | `monitor_instance_id` 仍能解析到实例 | P1 |
| E-08 | 单指标扫描回归 | 普通 metric 策略 | 阈值、恢复、无数据逻辑与旧版本一致 | P0 |

## 历史兼容测试

| ID | 历史策略类型 | 操作 | 期望结果 | 优先级 |
| --- | --- | --- | --- | --- |
| C-01 | 历史单指标 `metric` | 打开编辑页 | 回填为一行指标 | P0 |
| C-02 | 历史单指标 `metric` | 不修改直接保存 | 保存成功，结构仍为 `metric` | P0 |
| C-03 | 历史 filter 无 `logic` | 打开后直接保存 | 不因缺少 AND/OR 报错 | P0 |
| C-04 | 历史 `pmq` | 扫描 | 继续兼容扫描 | P0 |
| C-05 | 历史 `pmq` | 预览 | 继续兼容预览 | P1 |
| C-06 | 普通新建页 | 查看指标区域 | 不出现 PromQL 输入框 | P0 |

## API 级验证清单

| ID | Payload 类型 | 构造点 | 期望 |
| --- | --- | --- | --- |
| A-01 | `metric` | `group_by=["instance_id","x) or vector(1"]` | serializer 拒绝 |
| A-02 | `metric` | `filter.value=["checkout"]` | serializer 拒绝 |
| A-03 | `formula` | `queries[0].group_by=["instance_id","x) or vector(1"]` | serializer 拒绝 |
| A-04 | `formula` | `queries[1].metric_id=999999` | serializer 拒绝 |
| A-05 | `formula` | `expression="b / a"` | serializer 接受；anchor 仍为 `queries[0]`，最终 group_by 使用首行指标维度 |
| A-06 | `formula` | `queries[0].group_by=["status"]` | serializer 拒绝 |
| A-07 | `formula` | `queries[1].group_by` 含锚点外维度 | serializer 拒绝 |

## 推荐执行顺序

| 顺序 | 类型 | 内容 |
| --- | --- | --- |
| 1 | 自动化单测 | 跑后端公式、serializer、扫描聚焦用例 |
| 2 | 前端脚本测试 | 跑公式 payload 转换、校验和模式切换脚本 |
| 3 | API 边界测试 | 直接构造非法 payload，验证后端拒绝 |
| 4 | 页面 E2E | 新建单指标、单转多、多转单、多指标保存预览 |
| 5 | 扫描语义 | 用 mock VM 数据覆盖阈值、无数据、除零 |
| 6 | 历史兼容 | 旧 `metric` 和 `pmq` 策略打开、预览、扫描 |

## 建议自动化命令

后端聚焦回归：

```bash
cd server
DJANGO_SETTINGS_MODULE=settings INSTALL_APPS=system_mgmt,monitor,cmdb DB_ENGINE=sqlite DB_NAME=':memory:' MINIO_ENDPOINT=127.0.0.1:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=testtesttest MINIO_USE_HTTPS=false uv run pytest -o addopts='' apps/monitor/tests/test_metric_query_utils.py apps/monitor/tests/test_serializers_extra.py apps/monitor/tests/test_formula_expression_parser.py apps/monitor/tests/test_formula_condition_compiler.py apps/monitor/tests/test_formula_validator.py apps/monitor/tests/test_formula_compiler.py apps/monitor/tests/test_formula_policy_preview.py apps/monitor/tests/test_formula_policy_scan.py apps/monitor/tests/test_monitor_policy_serializer_validation.py apps/monitor/tests/test_policy_calculate_service.py apps/monitor/tests/test_policy_scan_metric_query_service.py -q
```

前端聚焦回归：

```bash
cd web
./node_modules/.bin/tsx scripts/monitor-policy-formula-payload-test.ts
./node_modules/.bin/eslint "src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts" "src/app/monitor/(pages)/event/strategy/detail/page.tsx"
```

## 验收结论标准

| 结论项 | 标准 |
| --- | --- |
| 单指标 | 只有一行指标时保存为 `metric`，行为与旧版本一致 |
| 多指标 | 多行指标保存为 `formula`，必须填写结果名称和表达式 |
| 模式切换 | 1 行为 `metric`，多行为 `formula`，反复切换不死锁 |
| 历史兼容 | 旧策略打开后不修改也能保存 |
| 安全边界 | 非法 filter/group_by/metric_id/表达式不能落库 |
| 告警语义 | 只基于公式最终结果告警，无数据也基于最终结果 |
| 非有限值 | `inf/-inf/nan` 不触发阈值告警，也不产生错误恢复 |

## 口径说明

- 多指标公式统一以 `query_condition.queries[0]` 作为 anchor。表达式变量出现顺序不改变最终告警身份、维度或实例归属。
- 因此 `a / b`、`b / a`、`(b / a) * 100` 均可作为合法表达式；只要所有变量存在、均被引用、至少引用两个不同变量，且非 anchor 指标维度不包含 anchor 外额外维度即可。
