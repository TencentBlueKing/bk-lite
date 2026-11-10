# 01 — 聚合层规则文档与 ADR

Status: ready

Blocked by: None（总顺序上排在 `rum-session-end-records`、`apm-policy-merged-queries` 之后）

**What to build:** 运维拿到一份文档，就能独立部署聚合库、配置两个写入进程、接好告警，并按其中的验收清单判定合格；
仓库里的架构决定与长期规范不再写“APM 禁止 VictoriaMetrics / Span Metrics”。

- [ ] 新增运维规则文档（`docs/operations/` 下）：部署要求（独立单节点、≥35 天保留、只走内网、可选基础认证）、
      环境变量（`AGG_VICTORIAMETRICS_WRITE_URL`、`AGG_VICTORIAMETRICS_QUERY_URL`、认证变量、`APM_AGG_SHARD`、`RUM_AGG_SHARD`）、
      写入规则（spec「聚合库」一节）、标签禁区、告警（磁盘 70%/85%、序列数异常、remote write 失败/丢弃）、容量参考、
      两个镜像新增组件与稳定性等级、启动不依赖、验收清单（对应 p398_930 验收 1–7）
- [ ] 新 ADR（编号顺延）：部分替代 ADR 0006，内容见 spec「架构决定」；ADR 0006 头部注明被部分替代
- [ ] 同步长期规范：APM 架构与功能清单 capability、产品决策文档（apm-data-plane、apm-inferred-downstream）中的相关表述；
      基础设施清单 capability 增加聚合库一行
- [ ] 文档内链接有效；不改任何代码与部署文件（`deploy/apm` 的验收清单与配置测试在 02 改）

## Notes

- 运维文档面向人，写清“必须满足的硬约束”和“编排自选”的边界，沿用 `deploy/apm` 的“契约硬、编排软”写法。
