# Ops Analysis Period Compare

Status: done

## Migration Context

- Legacy source: `openspec/changes/ops-analysis-period-compare/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

当前运营分析存在两条相似但分散的数据消费链路：

1. 仪表盘
   - `widgetWrapper.tsx` 负责生成请求参数并调用 `getSourceDataByApiId()`
   - 单值卡通过 `selectedFields[0]` 从原始结果中取展示值
2. 拓扑
   - `useGraphOperations.ts` 为单值节点单独构造请求参数并调用 `getSourceDataByApiId()`
   - 单值节点同样通过 `selectedFields[0]` 从原始结果中取展示值

两侧共享同一个 `ValueConfig` 和同一个数据源接口，但取数逻辑并没有集中。若直接把 compare 需求分别加到仪表盘和拓扑页面中，会出现：

- 基线时间计算和双请求逻辑复制两份
- 后续修复 compare 边界时需要双边同步修改
- 为了单次请求去改 `operation_analysis` 和 NATS 接口，会把 compare 语义压到底层

日志分析页已经给出一个更符合现状的参考实现：原始接口仍然只查单周期，前端页面层通过“当前周期 + 基线周期”双请求完成 compare。本设计沿用该思路，但不把逻辑散落到仪表盘和拓扑各自页面，而是集中到运营分析共享 compare 查询层。

## Goals / Non-Goals

**Goals:**

- 让 compare 配置通过 `ValueConfig` 在仪表盘和拓扑间共享
- 让 compare 查询逻辑集中在一个共享层，而不是分别散落在仪表盘和拓扑取数代码中
- 复用现有单周期数据源接口，不要求 `operation_analysis` 或 NATS 接口支持 compare 协议
- 对齐日志分析页的基线周期时间规则
- 第一阶段同时覆盖仪表盘单值卡和拓扑单值节点

**Non-Goals:**

- 不把 compare 做成后端统一协议
- 不要求每个 NATS 接口重写为原生支持 compare
- 不要求所有图表类型在本次都支持 compare
- 不扩展到“上周同期”“上月同期”“自定义基线”等多 compare 模式

## Decisions

### 1. compare 配置挂在共享 `ValueConfig`

`ValueConfig` 新增：

```ts
compare?: boolean
```

仪表盘组件和拓扑单值节点都复用这一配置，不再为两侧定义独立 compare 配置模型。

**理由**:

- 两侧都已经复用 `ValueConfig`
- compare 是否开启本质上属于组件取数配置，而不是页面级状态
- 统一类型后，拓扑和仪表盘都能走同一条 compare 查询能力

### 2. compare 查询逻辑集中在共享前端层

新增一层共享 compare loader / hook，用于统一完成：

1. 基于 `ValueConfig` 和统一筛选计算有效请求参数
2. 识别当前请求中的时间范围参数
3. 生成基线周期参数
4. 发起两次同构单周期请求
5. 输出统一的查询结果模型，例如：

```ts
{
  currentData: unknown
  baselineData?: unknown
}
```

仪表盘 `widgetWrapper` 和拓扑 `useGraphOperations` 都只消费这层输出，不再各自计算基线时间窗。

**理由**:

- 满足“逻辑尽量集中，不要太散”
- 同时覆盖仪表盘和拓扑，不复制 compare 逻辑
- 后续若要改 compare 实现方式，只需改共享层，不必同时改两侧页面

### 3. compare 不新增后端请求参数协议

参考日志分析页，本次 compare 不向后端接口新增 `compare=true` 或 `compare.type` 之类参数。共享 compare 查询层直接发起两次原始请求：

- 当前周期请求
- 基线周期请求

两次请求除时间范围外，其他参数必须完全一致。

**理由**:

- `operation_analysis` 当前只是透传层，不理解业务 compare 语义
- 如果新增 compare 参数并下沉到底层，很多 NATS 接口都要一起改造
- 复用现有单周期接口，成本最低，也最贴近日志分析页现状

### 4. compare 只对存在可识别时间参数的数据源开放

共享 compare 查询层只对这类配置生效：

- 有且仅有一个有效的 `timeRange` 参数来源
- 该时间参数在当前请求中能被稳定解析为 `[start, end]`

若不满足该条件，则 compare 不应启用，或在配置层禁用。

**理由**:

- compare 的核心前提就是能构造基线时间窗
- 不强行支持没有时间参数的数据源，避免产生不可解释的 compare 行为

### 5. 时间规则与日志分析页保持一致

基线周期采用日志分析页同款规则：

```text
duration = current_end - current_start
baseline = [current_start - duration, current_start]
```

该规则适用于：

- 绝对时间范围
- 相对时间范围（先解析成当前请求的实际起止时间，再计算基线周期）

**理由**:

- 与现有日志分析页行为一致，降低产品理解和验收成本
- 不引入自然周、自然月等额外语义

### 6. compare 展示结果仍由消费端计算

共享 compare 查询层只输出 `currentData` 和 `baselineData`。不同消费端自己决定如何展示：

- 仪表盘单值卡：显示主值、较上一周期百分比、方向
- 拓扑单值节点：根据节点展示能力决定如何显示当前值与变化信息

**理由**:

- 不要求数据源接口负责展示层摘要逻辑
- 拓扑节点和仪表盘单值卡的可视化能力并不完全相同
- 查询层只负责“拿两组数据”，展示逻辑由消费端各自处理更合理

## Risks / Trade-offs

| 风险 | 缓解措施 |
| --- | --- |
| compare 逻辑虽然不下沉后端，但若共享层设计不好，仍可能在仪表盘和拓扑分别复制 | 明确要求 compare 双请求、时间推导、结果模型只存在一处共享实现 |
| 某些数据源没有稳定 timeRange 参数，无法支持 compare | 在配置层按数据源能力控制 compare 开关可用性 |
| 仪表盘和拓扑的展示形态不同，无法完全共用展示逻辑 | 仅共享查询层和配置层；展示层只共享输入 contract，不强行共用 UI |
| 页面 compare 开启后请求数翻倍 | 第一阶段仅覆盖单值类场景，后续若性能成为问题，再考虑把共享层下沉到 `operation_analysis` 做服务端聚合 |

## Implementation Notes

- 共享 compare 查询层应建立在现有 `buildWidgetRequestParams` / `processDataSourceParams` 基础上，避免重复实现参数合并。
- 仪表盘和拓扑都应通过同一套 compare 时间推导工具函数计算基线周期。
- 字段探测（配置时读取字段树）仍然走原来的单周期请求，不需要 compare 参与。
- 若后续 compare 能力要扩展到折线、表格，优先复用这层共享查询能力，而不是在新组件里重新写双请求逻辑。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-26
```

## Capability Deltas

### ops-analysis-period-compare

## ADDED Requirements

### Requirement: 共享 compare 配置

系统 SHALL 通过共享 `ValueConfig` 为运营分析单值类配置声明是否开启“相对上个周期变化”，并允许仪表盘组件和拓扑单值节点复用同一 compare 配置语义。

#### Scenario: 仪表盘单值卡开启 compare
- **WHEN** 用户为仪表盘单值卡开启 compare 开关
- **THEN** 系统保存该组件的 compare 配置为开启状态

#### Scenario: 拓扑单值节点开启 compare
- **WHEN** 用户为拓扑单值节点开启 compare 开关
- **THEN** 系统保存该节点的 compare 配置为开启状态

#### Scenario: 无有效时间参数时不可开启 compare
- **WHEN** 单值类配置不存在可识别的有效时间范围参数
- **THEN** 系统不应允许该配置启用 compare

---

### Requirement: 共享 compare 查询层

系统 SHALL 通过一层共享的前端 compare 查询能力处理 compare 取数，避免仪表盘和拓扑分别实现基线时间计算和双请求逻辑。

#### Scenario: 仪表盘与拓扑复用同一 compare 查询层
- **WHEN** 仪表盘单值卡和拓扑单值节点都开启 compare
- **THEN** 两者都通过同一共享 compare 查询层获取 compare 数据

#### Scenario: compare 查询层输出统一结果模型
- **WHEN** compare 查询完成
- **THEN** 共享 compare 查询层至少向消费端输出 `currentData` 和 `baselineData`

---

### Requirement: compare 复用原始单周期接口

系统 SHALL 参考日志分析页做法，通过两次同构单周期请求完成 compare，而不是要求后端或 NATS 接口原生支持 compare 协议。

#### Scenario: compare 不修改后端接口协议
- **WHEN** 组件开启 compare
- **THEN** 系统继续调用现有单周期数据源接口
- **AND** 不要求后端接口新增 compare 请求参数

#### Scenario: compare 双请求除时间外参数一致
- **WHEN** 共享 compare 查询层构造当前周期请求和基线周期请求
- **THEN** 两次请求除时间范围外的所有参数必须保持一致

---

### Requirement: compare 基线周期时间规则

系统 SHALL 将基线周期定义为与当前时间范围等长、紧邻当前周期之前的时间窗，并与日志分析页现有规则保持一致。

#### Scenario: 相对时间范围基线计算
- **WHEN** 当前时间范围为最近 15 分钟
- **THEN** 基线周期为其之前连续的 15 分钟时间窗

#### Scenario: 绝对时间范围基线计算
- **WHEN** 当前时间范围为用户选择的绝对起止时间
- **THEN** 基线周期应通过当前时间窗长度回推得到

---

### Requirement: 前端消费端负责 compare 展示计算

系统 SHALL 由前端消费端基于 `currentData` 和 `baselineData` 计算 compare 展示结果，不要求数据源接口预先返回差值、变化率或方向。

#### Scenario: 仪表盘单值卡计算较上一周期结果
- **WHEN** 仪表盘单值卡已配置 `selectedFields[0]`
- **THEN** 前端应从 `currentData` 和 `baselineData` 中按相同字段路径取值并计算变化结果

#### Scenario: 拓扑单值节点复用同一 compare 数据模型
- **WHEN** 拓扑单值节点需要展示 compare 结果
- **THEN** 前端应基于共享 compare 查询层输出的 `currentData` 和 `baselineData` 完成节点展示逻辑

## Work Checklist

## 1. 共享配置与能力边界

- [x] 1.1 在 `web/src/app/ops-analysis/types/dashBoard.ts` 的 `ValueConfig` 中增加 `compare?: boolean` 字段，供仪表盘和拓扑共用。
- [x] 1.2 在仪表盘组件配置面板和拓扑节点配置面板中接入同一 compare 开关语义。
- [x] 1.3 明确 compare 仅对存在有效 `timeRange` 参数的单值类配置可用，不满足条件时禁用 compare。

## 2. 共享 compare 查询层

- [x] 2.1 基于现有参数构建逻辑抽出共享 compare loader / hook，统一复用 `buildWidgetRequestParams` / `processDataSourceParams` 结果。
- [x] 2.2 在共享 compare loader 中实现时间参数识别与基线周期推导，规则与日志分析页一致：`baseline = [current_start - duration, current_start]`。
- [x] 2.3 在共享 compare loader 中发起两次同构单周期请求，并统一输出 `currentData` / `baselineData` 结果模型。
- [x] 2.4 确保共享 compare loader 的双请求除了时间范围外不修改任何其他参数。

## 3. 仪表盘接入

- [x] 3.1 在 `web/src/app/ops-analysis/(pages)/view/dashBoard/components/widgetWrapper.tsx` 中接入共享 compare loader，移除页面内分散的 compare 逻辑。
- [x] 3.2 在仪表盘单值卡中使用 `selectedFields[0]` 从 `currentData` 和 `baselineData` 提取值。
- [x] 3.3 在仪表盘单值卡中统一计算“较上一周期”的差值、变化百分比与方向。

## 4. 拓扑接入

- [x] 4.1 在 `web/src/app/ops-analysis/(pages)/view/topology/hooks/useGraphOperations.ts` 中接入共享 compare loader，避免单值节点自行实现 compare 双请求。
- [x] 4.2 在 `web/src/app/ops-analysis/(pages)/view/topology/components/nodeConfPanel.tsx` 中接入 compare 配置开关，并保持与仪表盘配置语义一致。
- [x] 4.3 定义拓扑单值节点在 compare 开启时的展示策略，确保不额外复制时间推导和请求逻辑。

## 5. 验证

- [x] 5.1 验证 compare 关闭时，仪表盘与拓扑仍按原单周期请求工作，不影响现有数据源接口。
- [x] 5.2 验证 compare 开启时，仪表盘和拓扑都通过同一共享 compare loader 获取当前周期与基线周期数据。
- [x] 5.3 验证绝对时间和相对时间两种场景下，基线周期计算结果符合日志分析页“等长紧邻前窗”规则。
- [x] 5.4 验证无需修改 `operation_analysis` 和底层 NATS 接口协议即可完成 compare 功能。
