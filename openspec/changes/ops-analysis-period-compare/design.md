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
