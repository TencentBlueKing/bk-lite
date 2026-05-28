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
