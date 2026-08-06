# APM 设计能力服务化

Status: superseded by `specs/changes/apm-nats-vt-pipeline/spec.md`

> 本文件保留 SLO、拓扑权限和无数据语义的历史来源；VictoriaMetrics 查询与逐 Trace 拓扑扫描已经废弃，当前实现契约改由 VictoriaTraces-only Adapter 和 dependencies 接口承担。

## 背景

`apm-mvp` 只承诺接入、目录、RED、Trace 与基础告警；Storybook 中的拓扑、SLO、Issue 聚类等能力被明确排除。生产路由现已按产品信息架构展示这些页面，因此不能继续依赖静态样例或浏览器内状态。

本变更在不改变 APM 数据面边界的前提下，优先服务化能够由现有 VictoriaMetrics / VictoriaTraces 正确推导的能力。原始 Span 与派生指标仍不写 PostgreSQL，外部存储不可用仍以可重试的降级响应呈现。

## 本期范围

1. SLO 持久化 CRUD、启停和实时评估：
   - 服务级或端点级；环境必填；
   - 可用性、P95 时延、P99 时延三种 SLI；
   - 滚动 7 天、滚动 30 天或自然月；
   - 返回当前达标率、目标、错误预算剩余和 `available/no_data` 数据状态。
2. SLO 指标计算由 `MetricStore` 的小接口隐藏 PromQL；生产使用 VictoriaMetrics adapter，测试使用内存 adapter。
3. SLO 读取与服务可见性一致，写操作使用 `services-Operate`；越权服务与不存在服务不可枚举。
4. 遥测存储不可用不影响 SLO 元数据读取。单个 SLO 的评估失败返回该项的降级状态，不让整页伪装为空。
5. 服务拓扑从当前组织可见的真实 Trace 父子 Span 关系聚合：
   - 查询窗口最大 7 天，并限制服务/环境目标数和每目标 Trace 样本数；
   - 返回采样 Trace 数与 `truncated`，不得把有界样本描述成全量调用图；
   - 拓扑目标按 `ApmServiceOrganization` 判定，与服务目录及服务级聚合一致，不受实例组织变化影响；
   - Trace 详情仅作为有界聚合输入，节点与边必须再次限制在当前组织可见的服务身份集合内，避免通过相邻调用泄漏其他组织服务；
   - 节点与边的健康状态仅表示样本内错误比例，不等同于告警状态。

## 明确不在本切片伪造的能力

- Issue 必须使用稳定错误指纹和样本 Trace；简单按错误 Trace 标题分组不视为完整聚类。
- 90 天 SLO 超过当前 VictoriaMetrics 默认 30 天保留期，本期不开放。
- 多级告警阈值需要新的策略领域模型，不用一条现有策略伪装成三级阈值。

## 接口

| 路径 | 能力 |
| --- | --- |
| `/api/v1/apm/slos/` | 列表、创建 |
| `/api/v1/apm/slos/{id}/` | 详情、编辑、删除 |
| `/api/v1/apm/slos/{id}/enable/` | 启用 |
| `/api/v1/apm/slos/{id}/disable/` | 停用 |
| `/api/v1/apm/topology/` | 按时间窗、可选环境查询有界服务调用图 |

## 计算语义

- 可用性：`(总调用 - 错误调用) / 总调用 × 100%`。
- 时延：`耗时不高于阈值的调用 / 总调用 × 100%`，必须从直方图桶计算，不能用 P95/P99 的单点值替代事件占比。
- 错误预算剩余：`max(0, (允许失败率 - 当前失败率) / 允许失败率 × 100%)`。目标为 100% 时，当前达标率为 100% 才返回 100%，否则返回 0%。
- 无样本时所有计算值为 `null`，`data_state=no_data`，不得返回伪造的 0。
