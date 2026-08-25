# 网络状态拓扑改为勾选设备闭集

Status: implemented

## Problem Statement

运营分析「网络状态拓扑」现在必须先选一台中心设备和展开深度，后端按 CMDB 接口直连做 BFS。不在这棵连通分量里的交换机、路由器、防火墙加不进来。巡检大屏经常需要把几台没有互连、甚至跨模型的设备放在同一张图上，再按它们之间实际存在的关联排版。

## Solution

组件设置改为跨网络模型勾选设备。画布节点严格等于这份列表；连线只画它们之间已有的接口直连。有连线的连通块自动排并铺开；完全没有连线的点堆在右下角，用户再拖。没有新设备列表的老配置、列表里个别设备无效、超过上限，都直接失败并提示重新配置。

## User Stories

1. As an 运维人员, I want 在组件设置里跨交换机/路由器/防火墙勾选要看的设备, so that 不在同一组关联上的设备也能进同一张图
2. As an 运维人员, I want 按模型筛选设备列表，并且选项和节点上能看出每台是什么模型, so that 我不会勾错设备
3. As an 运维人员, I want 组件只展示我勾选的设备，并用它们之间已有的关联自动布局, so that 图上不会冒出我没选的邻居
4. As an 运维人员, I want 互相有连线的几坨设备自动铺开、完全没线的点堆在右下角, so that 孤岛不会挡住主拓扑，我还可以自己拖位置
5. As an 运维人员, I want 在组件里调整节点上限（默认 100，最多 200）, so that 小屏可以少选、大图可以多选，又不会把查询打爆
6. As an 运维人员, I want 老配置或缺设备、个别设备无效时明确提示重新配置, so that 我不会以为图还在按旧的中心+深度展开
7. As a 查看者, I want 点选告警节点仍能看告警弹框、该节点仍被强调, so that 取消通往中心的故障路径后，处置入口还在

## Implementation Decisions

- 范围是运营分析网络状态拓扑场景组件（含内置大屏及用户画布上的同一组件）。不改 CMDB 网络拓扑编辑页的中心+深度 BFS，也不改独立「网络拓扑」画布。
- 配置从「模型 + 单实例 + 深度」改为设备 UUID 列表 `instUuids` 与节点上限 `nodeLimit`。模型筛选只存在于设置面板，不写入配置。新写入不再输出 `modelId` / `instUuid` / `depth`。
- 画布节点闭集：结构接口只返回勾选且校验通过的设备。连线是这些设备之间已有的接口直连诱导子图；连到未勾选设备的边不出现，也不把对端拉进图。
- 任一选中设备不存在、无查看权限、或不是带 `interface belong` 的网络设备：整次失败，不偷偷少画。列表不允许重复。空列表与缺 `instUuids`（含只有旧 `instUuid`+`depth` 的存量）视为未配置，前端不取数，展示重新配置。
- 节点上限：默认 100，设置可填 1～200，勾选数不能超过该上限。超过组件上限或系统硬顶 200，接口失败，不截断。CMDB 编辑页 BFS 仍用现有 100 上限，不借此扩大编辑页扩散。叠色 `get_monitor_ids_by_inst_uuids` 与接口运行态 `query_latest_interface_metrics` 的批量上限与硬顶对齐为 200，避免图画出来、状态查不全。
- 结构取数不再走中心 BFS。对每个选中设备查一跳接口直连，只保留两端都在选中集合内的边；节点 ID 仍映射为 `inst_uuid`。响应不再把某台设备当中心根：`center_id` 可空或省略，前端不再用它做布局或故障路径。节点带 `model_id`（及名称），画布图标/副标题继续展示模型。
- 自动布局在场景组件侧完成，不改 CMDB 编辑页布局算法。有边的连通块沿用现有层级/力导向/环形，每块自选局部根（度数最高的点），多块并排铺开互不重叠；度为 0 的点统一堆在画布右下角。用户拖过的位置仍按布局模式持久化。
- 取消「选中告警节点通往中心」的故障路径高亮。点选仍强调该节点，告警角标/弹框/叠色/端口流量/通断不变。
- 内置「网络状态拓扑大屏」改为设备列表配置，描述不再写「以某实例为中心」。演示环境需填入真实设备 UUID；未填或无效则走重新配置，不为内置大屏保留旧 BFS。
- 报表渲染允许列表从冻结配置收集 `instUuids`，不再只认一对 `(modelId, instUuid)`。分享与叠色数据源允许范围不因本变更改口径，只是查询批次上限改为 200。

## Testing Decisions

- 好测试只验证外部行为：给定设备 UUID 列表，返回的节点集合是否等于该列表、连线是否只连接列表内设备、未选对端是否不出现；缺列表/重复/缺失/无权限/非网络设备/超上限是否失败；连通块与孤岛布局是否可观察（孤岛在右下、有边的块不重叠）；设置提交是否写出 `instUuids`+`nodeLimit` 且不再要求中心+深度；叠色/接口批量拒绝超过 200。不锁定 X6 内部 DOM 或 Neo4j Cypher。
- 接缝与 prior art：
  - 请求序列化与场景结构服务：对齐现有 `network_status_topology` 视图/序列化/服务单测（改为列表参数与 fail-closed）
  - CMDB 诱导子图：对齐现有 `network_topology` 单测风格（mock 图查询、权限、去重），新增「只保留两端都在集合内的边、孤岛节点仍在」
  - 前端 fetch：现有网络状态拓扑 fetch 测试改为带 `instUuids`；无列表时不请求并展示重新配置
  - 配置提交与布局持久化：现有 `submitConfig.networkStatusTopology` 与 `networkStatusTopologyLayout` 测试改为新字段
  - 布局纯函数：连通块打包与右下孤岛（新测，不改 CMDB 编辑页布局单测）
  - 监控/CMDB 批量 NATS：现有「超过上限拒绝」断言从 100 改为 200
  - 报表 render token：允许目标从 `instUuids` 收集
- 不强制本阶段做完整大屏 E2E。手动验收：跨模型勾选、有关联的排在一起、没关联的在右下角可拖；老组件打开报重新配置；上限可改到 200。

## Out of Scope

- CMDB 网络拓扑编辑页的中心+深度 BFS、节点上限 100、点开邻居继续展开
- 独立「网络拓扑」画布的 WeOps 取数与配色
- 把未勾选的邻居作为「建议加入」或二次确认
- 存量中心+深度配置的自动迁移或双读
- 通往中心的故障路径高亮（本变更删除，不改成高亮整块连通图）
- 超过 200 的节点规模、分页勾选之外的另套设备目录
- 在画布上直接添加/删除设备（只在设置里改列表）
- 改变叠色、端口流量、通断、悬停指标或布局分桶持久化语义

## Further Notes

- 「孤岛」只指诱导子图里度为 0 的点。两坨彼此有内部连线、但坨与坨之间没线的，算多个连通块，自动铺开，不塞进角落。
- 层级布局不再依赖全局中心；每块连通图用局部根。力导向/环形同样按块计算后再平移打包。
- 硬顶 200 是场景组件与其叠色/接口批量查询的共同上限，不是把 CMDB 编辑页 BFS 也抬到 200。

## Completion Evidence

Status: implemented

- 配置与取数：场景组件改为 `instUuids` + `nodeLimit`（默认 100，硬顶 200）。缺列表/只有旧中心+深度不取数，展示重新配置。结构接口请求体为 `{ inst_uuids, node_limit }`。勾选数超过上限时设置校验失败；后端序列化同样拒绝。
- CMDB `network_topology_among_uuids`：节点等于勾选集合，边只保留两端都在集合内；个别设备无效整次失败。CMDB 编辑页 BFS 上限仍为 100。
- 画布：连通块打包铺开，度为 0 的孤岛在右侧；取消通往中心的故障路径。点选强调与告警弹框保留。连线运行态（流量/通断/端口悬停）仍接在叠色之后。
- 聚焦测试（2026-08-19）：
  - `cd web && ./node_modules/.bin/vitest run src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/linkRuntimeModel.test.ts src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/overlayModel.test.ts src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/statusTopologyGraph.badge.test.ts src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/networkStatusTopology.fetch.test.tsx src/app/ops-analysis/components/widgetConfig/hooks/__tests__/useNetworkStatusTopologyConfig.test.ts src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/closedSetLayout.test.ts`：**72 passed**
  - `cd web && ./node_modules/.bin/tsx --test src/app/ops-analysis/utils/__tests__/networkStatusTopologyLayout.test.ts src/app/ops-analysis/components/widgetConfig/utils/__tests__/submitConfig.networkStatusTopology.test.ts src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/popoverPosition.test.ts`：**42 passed**
  - 后端带 `--reuse-db` 的 pytest 本次被本机其他 Django 测试占用测试库，未能完成新鲜跑通。相关单测文件已按闭集/200 上限改完：`test_network_topology_service.py` AmongUuids、`test_network_status_topology.py`、`test_get_monitor_ids_by_inst_uuids_nats.py`、接口批量上限。
- 未做完整大屏 E2E。手动验收仍按 Testing Decisions：跨模型勾选、有关联的排在一起、没关联的在右下角可拖；老组件打开报重新配置；上限可改到 200。
