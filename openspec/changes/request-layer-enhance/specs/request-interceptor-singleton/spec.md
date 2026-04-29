## ADDED Requirements

### Requirement: 拦截器模块级单例注册
request/response 拦截器 SHALL 在模块加载时注册一次，不在 `useApiClient` hook 的 `useEffect` 中重复注册。

#### Scenario: 多组件同时使用 useApiClient
- **WHEN** 页面中有 N 个组件/hook 调用 `useApiClient()`
- **THEN** apiClient 上 SHALL 只有 1 对 request + response 拦截器，而非 N 对

### Requirement: Token 通过 setter 注入
`useApiClient` SHALL 通过模块级 `setToken()` 函数将 token 写入 `tokenRef`，拦截器从 `tokenRef.current` 读取。

#### Scenario: token 更新后请求携带新 token
- **WHEN** session 中的 token 发生变化
- **THEN** 后续所有请求的 Authorization header SHALL 使用新 token

#### Scenario: token 为空时拦截请求
- **WHEN** `tokenRef.current` 为 null
- **THEN** request 拦截器 SHALL reject 并抛出 'No token available' 错误
