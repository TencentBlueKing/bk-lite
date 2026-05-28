## Why

运营分析的仪表盘单值卡和拓扑单值节点都已经具备 compare 的关键前提：

- 通过 `ValueConfig.selectedFields` 显式声明展示字段
- 通过数据源参数中的 `timeRange` 表达当前周期
- 通过 `getSourceDataByApiId()` 获取单周期原始数据

但当前 compare 逻辑还没有统一落点。如果分别在仪表盘组件、拓扑节点和底层 NATS 接口中各自实现“相对上个周期变化”，会很快出现问题：

- compare 配置无法在仪表盘和拓扑间复用
- 时间推导和双请求逻辑分散，后续维护容易漂移
- 为了支持 compare 去改每个 NATS 接口，代价高且侵入过深

日志分析页已经验证了一条更符合现状的方案：后端接口保持单周期原始查询，前端通过两次同构请求获取当前周期和基线周期，再自行计算变化结果。本次 change 参考日志分析的实现方式，并把 compare 逻辑集中到运营分析共享查询层，同时覆盖仪表盘和拓扑两侧。

## What Changes

- 为运营分析共享的 `ValueConfig` 增加 compare 开关配置，供仪表盘组件和拓扑单值节点共同使用
- 新增一层前端共享 compare 查询能力，统一负责：识别时间参数、推导基线周期、发起双请求、输出 `currentData` / `baselineData`
- 仪表盘单值卡和拓扑单值节点都通过这层共享 compare 查询能力取数，不在各自页面里复制 compare 逻辑
- compare 时间规则对齐日志分析页：基线周期取“与当前时间窗等长、紧邻当前周期之前的时间窗”
- 后端 `operation_analysis` 接口和底层 NATS 接口保持单周期原始查询语义，不新增 compare 协议

## Capabilities

### New Capabilities

- `ops-analysis-period-compare`: 运营分析单值类配置可开启“相对上个周期变化”，并通过共享前端 compare 查询层获取当前周期与基线周期两组数据。

### Modified Capabilities

- 无

## Impact

- **共享前端类型与查询层**:
  - `web/src/app/ops-analysis/types/dashBoard.ts`
  - `web/src/app/ops-analysis/utils/widgetDataTransform.ts`
  - 新增共享 compare query/loader 工具或 hook
- **仪表盘**:
  - `web/src/app/ops-analysis/(pages)/view/dashBoard/components/widgetWrapper.tsx`
  - `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig/`
  - 单值组件 compare 展示
- **拓扑**:
  - `web/src/app/ops-analysis/(pages)/view/topology/hooks/useGraphOperations.ts`
  - `web/src/app/ops-analysis/(pages)/view/topology/components/nodeConfPanel.tsx`
  - 单值节点 compare 取数与展示
- **后端 / NATS**:
  - 无协议变更要求，继续复用现有单周期数据源接口
- **不在本次范围**:
  - 不要求每个数据源/NATS 接口原生支持 compare
  - 不要求所有图表第一期都支持 compare UI
  - 不定义“上周同期”“上月同期”“自定义基线”等额外 compare 模式
