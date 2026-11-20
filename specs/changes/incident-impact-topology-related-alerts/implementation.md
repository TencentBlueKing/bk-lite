# 事故影响拓扑增强实施

Status: 已实施

证据：`server/apps/cmdb/tests/test_incident_impact_topology.py` 保留上周基础图，并覆盖一层全部关系、基础设施、目录失败不回退、上下文失败留图。`server/apps/alerts/tests/test_incident_impact_topology.py` 覆盖告警查询失败时图还在且只记一条日志。`server/apps/alerts/tests/test_incident_impact_topology_chain.py` 用事件经 `AlertBuilder` 生成告警和事故，经现有 NATS 处理函数看到网卡 21 条分页、机柜无告警、应用计入成员告警，事故成员不变。页面单测覆盖无告警、未知和应用层。sqlite 跑通，未启动 NATS、图库和整套中间件。

口径以同目录 `design.md` 为准。告警进程只通过 `CMDB.incident_impact_topology` 取结构和归属，不 import CMDB 服务。

## 缝

- CMDB `query_incident_impact_topology`：给定种子、假边、假模型关系和假上下文，返回基础图、一层候选、应用归属和成员。模型关系目录失败时抛错，不退回成只查 `run` / `connect`。上下文失败时基础图仍在，`context_status=unavailable`。
- 告警 `POST /alerts/api/incident/{id}/impact_topology/`：种子求交、告警计数、挑选 40/20、不写事故成员。CMDB 只经 RPC。
- 告警 `POST /alerts/api/incident/{id}/impact_topology_alerts/`：只返回这次图上的节点，每页 20 条。
- 页面 `buildImpactGraph`：关联对象、无告警、未知、应用层和未绑定可以区分。
- 链路：事件经 `AlertBuilder` 生成告警，再挂到事故上，经上述接口看关联对象告警和应用成员告警。事故成员集合不变。

## 步骤

1. 扩展现有 NATS `incident_impact_topology` 的返回，不新开第二个 CMDB 方法。基础桥接逻辑不动。另取种子模型的全部 `model_association`，再取这些 `model_asst_id` 下、一端是可见种子的实例边。候选最多 300。`ci_context` 在 CMDB 进程内点查。
2. 告警服务挑选有告警的候选最多 40、无告警的最多 20，桥接始终保留。按可见未关闭告警贴条数。应用成员合计超过 1000 时 `member_truncated`。
3. 侧栏另一次请求分页。图的响应不带告警明细。
4. 页面沿用影响拓扑画布，补节点状态、图例、侧栏分页和告警详情链接。
5. 用 sqlite 跑 CMDB 纯组装、告警接口，以及事件到事故的链路。不启动 NATS、图库和整套中间件。
