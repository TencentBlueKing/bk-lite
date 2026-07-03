# 监控策略双层汇聚发布核对清单

## 1. 发布范围

本次发布将监控策略汇聚配置从旧的单一 `algorithm` 模型调整为双层模型：

- `group_algorithm`：分组维度内的序列先如何聚合，支持 `avg/max/min/sum/count`。
- `algorithm`：汇聚周期内如何计算最终阈值判断值，支持 `avg_over_time/max_over_time/min_over_time/sum_over_time/count_over_time/last_over_time`。

策略预览、后台扫描、快照记录、批量模板创建和文件策略模板均应使用同一套语义。

## 2. 数据迁移规则

已创建策略通过迁移脚本补齐 `group_algorithm`，并将旧 `algorithm` 归一为窗口方法：

| 旧方法 | 新 `group_algorithm` | 新 `algorithm` |
| --- | --- | --- |
| `avg` / `avg_over_time` | `avg` | `avg_over_time` |
| `max` / `max_over_time` | `max` | `max_over_time` |
| `min` / `min_over_time` | `min` | `min_over_time` |
| `sum` / `sum_over_time` | `sum` | `sum_over_time` |
| `count` | `count` | `last_over_time` |
| `count_over_time` | `count` | `count_over_time` |
| `last_over_time` | `avg` | `last_over_time` |

模板文件也必须同时包含合法的 `group_algorithm` 和窗口型 `algorithm`。

## 3. 查询语义

统一查询结构：

```promql
<window_method>((<group_method>(metric) by (group_by))[period:step])
```

其中 `step = period / 30`，例如 `5m -> 10s`、`10m -> 20s`、`30m -> 1m`。

典型示例：

```promql
avg_over_time((avg(disk_used_percent) by (instance_id))[5m:10s])
max_over_time((max(metric) by (instance_id))[5m:10s])
last_over_time((count(metric) by (instance_id))[5m:10s])
last_over_time((avg(interface_status) by (instance_id,interface))[5m:10s])
```

## 4. 发布前检查

- 确认数据库迁移包含 `MonitorPolicy.group_algorithm` 字段新增和历史策略回填。
- 确认新建、编辑、预览策略请求均带上 `group_algorithm`。
- 确认后台扫描和策略预览生成的查询结构一致。
- 确认 `server/apps/monitor/support-files/plugins/**/policy.json` 中所有策略模板都使用新字段。
- 确认页面只暴露新的分组聚合方式和窗口汇聚方式组合，不再把旧单字段语义展示给用户。

## 5. 灰度验证建议

建议至少选择以下三类真实策略进行灰度：

| 场景 | 推荐配置 | 期望 |
| --- | --- | --- |
| 主机 CPU/内存使用率 | `avg + avg_over_time`，按实例分组 | 周期内平滑后的实例级趋势与预览一致 |
| 磁盘/网卡多维度指标 | `max + max_over_time` 或 `avg + avg_over_time`，按实例或接口分组 | 未选择维度被正确聚合，选择的维度输出独立序列 |
| 接口 up/down 状态 | `avg + last_over_time`，按实例和接口分组 | 最近窗口内每个接口输出最近有效状态 |
| 有效序列数量 | `count + last_over_time`，按实例分组 | 统计最近窗口内仍有数据的序列数量 |

灰度时需要同时对比：

- 策略预览曲线和后台扫描结果是否使用同一条查询。
- 告警对象维度是否符合用户选择的分组维度。
- COUNT/LAST 类状态指标是否符合产品预期。

## 6. 回滚注意点

- 回滚代码前，需要确认数据库中已存在的 `group_algorithm` 字段是否会被旧代码忽略或导致序列化异常。
- 如果回滚到旧代码但保留新模板，旧模板中的窗口型 `algorithm` 可能无法表达旧页面语义。
- 建议优先采用前向修复；确需回滚时，同步回滚策略模板和前端表单字段。

## 7. 当前验证命令

功能相关后端测试：

```bash
cd server && uv run pytest apps/monitor/tests/test_policy_preview_query.py apps/monitor/tests/test_metric_query_trigger_count.py apps/monitor/tests/test_monitor_policy_serializer_validation.py apps/monitor/tests/test_monitor_policy_group_algorithm_migration.py apps/monitor/tests/test_policy_bulk_payload.py apps/monitor/tests/test_policy_templates_aggregation.py -q
```

前端触达文件 lint：

```bash
cd web && ./node_modules/.bin/eslint src/app/monitor/types/event.ts src/app/monitor/hooks/event.tsx 'src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx' 'src/app/monitor/(pages)/event/strategy/detail/page.tsx' 'src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx' --ext .ts,.tsx
```

全量门禁：

```bash
cd server && make test
cd web && pnpm lint && pnpm type-check
```

## 8. 待人工确认

- 产品确认 `COUNT + LAST_OVER_TIME` 是否作为清单/有效序列数量的默认语义。
- 产品确认 `LAST_OVER_TIME` 是否统一使用双层结构，而不是恢复旧的 `any(last_over_time(metric[period])) by (...)`。
- 运维或发布负责人确认灰度环境中的真实策略样本和回滚窗口。
