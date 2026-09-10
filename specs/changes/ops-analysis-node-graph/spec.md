# 运营分析通信关系图

Status: implemented

## Problem Statement

运维人员在运营分析里已经能用 TopN 和表格看到 Flow 会话占用，但看不出主机之间、以及「谁在打哪个服务」的结构。他们希望在仪表盘上放一张有向流量图：节点是通信对象，边的方向和粗细表示真实流量。现有网络状态拓扑吃的是 CMDB 设备链路，关系拓扑吃的是带告警的实体关系，都铺不出 IP 会话图。

## Solution

新增一个通用数据源图表 `nodeGraph`（界面名「通信关系图」）。它和 TopN、表格一样绑 instant 排行结果，由组件把行聚成有向图。同一组件提供两种节点粒度：IP ↔ IP，以及源 IP → 目的 `IP:端口`（服务视角）。不新开 NATS，不改网络状态拓扑，不放宽关系拓扑契约。Flow 样例盘挂主机通信与访问服务两张图。

## User Stories

1. As a 看板搭建者, I want 在仪表盘或大屏上添加通信关系图并绑 instant 数据源, so that 任意有源/目的/流量字段的排行都能画成有向图。
2. As a 看板搭建者, I want 映射源字段、目的字段、流量字段，并切换 IP 或服务粒度, so that 同一数据既能看主机互访，也能看谁在访问哪些服务。
3. As an 运维人员, I want 看到有向边且边宽随流量变化, so that 能立刻认出大流量链路和通信方向。
4. As an 运维人员, I want 悬停节点和边时看到对象名和格式化后的流量, so that 不用先回到表格对数字。
5. As an 运维人员, I want 未选设备时图为空、不退化成全量, so that 行为与现有 Flow 排行组件一致。
6. As a 看板搭建者, I want 给图配置单位和换算系数, so that 边和悬停值能显示 Mbps 而不是原始 B/s。

## Implementation Decisions

- 图表类型 `nodeGraph`，走普通数据源图表路径（注册、配置提交、画布/大屏渲染）。不是 scene 组件，不自拉 CMDB，不出现在报表表面（报表仍只有表格类）。
- 不复用网络状态拓扑（设备实例 + 自拉拓扑）。不修改关系拓扑的节点身份/告警契约来塞流量边。
- 不新增监控查询。输入是现有 instant 行列表（会话行已有 `src`、`dst`、`dst_port`、`value`）。前端按配置字段取数并聚边。
- 受控指标排行数据源的可用图表补上 `nodeGraph`。其他数据源仅在声明该图表类型时可选。
- 组件配置：
  - 源字段、目的字段、流量字段（必填）
  - 粒度 `identityMode: ip | service`（必填，默认 `ip`）
  - `service` 时必填目的端口字段
  - 单位走与折线/饼图/TopN 相同的 `unitId`、换算系数、小数位
- 节点键：

```
ip:      source = row[sourceField]
         target = row[targetField]
service: source = row[sourceField]
         target = row[targetField] + ":" + row[targetPortField]
```

- 聚合：相同 `(source, target)` 的流量求和。源端口不上图。
- 丢弃：源或目的为空的行；`service` 下目的端口为空的行；源键与目的键相同的自环。丢弃单行不影响其余行。
- 边数不超过数据源 instant 上限（当前最大 100）。先按流量降序再截断，再布局。
- 布局：左右分栏。源节点在左、目的节点在右；同一地址兼具两种角色时分列出现。边从左到右，颜色表示流量、粗细随流量变化。节点大小固定。不保存节点坐标，刷新后重新布局。
- 悬停边：源、目的、格式化流量。悬停节点：节点名、入流量合计、出流量合计。第一期无点击下钻、框选、保存布局。
- 空结果走现有空状态；字段未配齐时不渲染图，提示补全映射。
- Flow 样例盘 YAML 在「通信关系」分组挂 `ip` 与 `service` 两张图，绑会话排行。

## Testing Decisions

只测外部行为：行到图的节点键与聚合、两种粒度、自环/缺字段丢弃、截断、左右分栏布局、配置提交与数据源声明、空数据。不测 X6 内部、真实 VM。

接缝：

- 纯函数：instant 行 → 节点/边（对齐关系拓扑 payload 解析测试、TopN 行展开测试）
- 配置提交：`nodeGraph` 持久化字段映射、粒度、单位（对齐 `submitConfig` 里 TopN / 关系拓扑用例）
- 图表类型列表与表面：仪表盘/大屏可选，报表不可选（对齐 `chartTypeList` / `chartTypeSurface`）
- 受控指标排行 `chart_type` 含 `nodeGraph`（对齐 Flow 数据源定义测试）
- 单位格式化复用现有可见值格式化，不新写一套（对齐 TopN/折线的单位用例）

## Out of Scope

- Sankey、热力图
- 两端都是 `IP:源端口 → IP:目的端口` 的五元组力导向图
- IP 外壳 + 端口内部节点的复合图
- 点击下钻、框选、持久化坐标
- 异常边/基线/新会话高亮
- 网段聚合
- 新 NATS 或 Flow 专用图查询
- 改网络状态拓扑或关系拓扑的数据契约

## Further Notes

产品决策：`docs/design/product-decisions/ops-analysis-node-graph.md`。  
与 Flow 第一期盘的关系：`docs/design/product-decisions/ops-analysis-flow-dashboard.md`、`specs/changes/ops-analysis-flow-dashboard/spec.md`。

验证（2026-09-03）：

- `cd web && node_modules/.bin/tsx --test`：`nodeGraphData`、`submitConfig.nodeGraph`、`chartTypeList`、`topologyMapWidgetContract` 共 25 passed
- `pnpm type-check`：`tsc -p tsconfig.build.json --noEmit` 通过
- `cd server && ... pytest apps/operation_analysis/tests/test_flow_dashboard_datasource_definitions.py --no-cov`：4 passed
- Flow 样例盘 YAML 含 `flow-node-graph-ip` / `flow-node-graph-service`；未改 `topologyMapData.ts` 与网络状态拓扑取数
