## ADDED Requirements

### Requirement: 自动模式请求
useRequest 在 auto 模式下 SHALL 在组件挂载时自动发起请求，并在 `refreshDeps` 变化时重新发起。

#### Scenario: 组件挂载自动请求
- **WHEN** 使用 `useRequest(fetchFn)` 且未设置 `manual: true`
- **THEN** SHALL 在挂载后自动调用 `fetchFn` 并将结果设置到 `data`

#### Scenario: refreshDeps 变化触发重新请求
- **WHEN** `refreshDeps` 数组中的依赖发生变化
- **THEN** SHALL 自动取消上一次请求并发起新请求

### Requirement: 手动模式请求
useRequest 在 manual 模式下 SHALL 不自动发起请求，仅通过 `run()` 方法触发。

#### Scenario: manual 模式不自动请求
- **WHEN** 使用 `useRequest(mutationFn, { manual: true })`
- **THEN** 挂载时 SHALL 不发起请求，直到调用 `run()`

### Requirement: 请求取消安全
useRequest SHALL 在组件卸载时取消进行中的请求，且兼容 React StrictMode。

#### Scenario: 组件卸载取消请求
- **WHEN** 组件在请求进行中被卸载（真实导航）
- **THEN** SHALL 通过 AbortController 取消进行中的请求

#### Scenario: StrictMode 双挂载不误取消
- **WHEN** React StrictMode 触发 mount → cleanup → re-mount
- **THEN** cleanup 阶段 SHALL 不取消请求（使用 setTimeout(0) 延迟，re-mount 时 clearTimeout）

### Requirement: 竞态安全
useRequest SHALL 确保只有最后一次请求的结果会更新 state。

#### Scenario: 快速连续请求
- **WHEN** 在短时间内触发多次请求（如快速切换 tab）
- **THEN** 前面的请求 SHALL 被取消，只有最后一次请求的结果更新到 `data`

### Requirement: 返回值接口
useRequest SHALL 返回 `{ data, loading, error, run, refresh, cancel }` 完整接口。

#### Scenario: loading 状态管理
- **WHEN** 请求发起到完成期间
- **THEN** `loading` SHALL 为 `true`，完成后变为 `false`
