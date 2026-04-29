## ADDED Requirements

### Requirement: HTTP 方法去除无意义 try/catch
get/post/put/del/patch 方法 SHALL 直接 `return handleResponse(await apiClient.xxx(...))` 而不用 `try { ... } catch { throw error }` 包装。

#### Scenario: 请求成功
- **WHEN** API 调用成功且 `result === true`
- **THEN** 方法 SHALL 直接返回 `data` 字段

#### Scenario: 请求失败
- **WHEN** API 调用失败（网络错误或 HTTP 错误）
- **THEN** 错误 SHALL 自然抛出，由 response 拦截器或调用方处理

### Requirement: handleResponse 去副作用化
`handleResponse` SHALL 只做 `{ result, data, message }` 的解析和提取，不调用 `message.error()` 也不接受 `onError` 回调参数。

#### Scenario: result 为 false
- **WHEN** 响应体中 `result === false`
- **THEN** `handleResponse` SHALL 抛出包含 `message` 的 Error，不弹 UI 提示

#### Scenario: blob 类型响应
- **WHEN** 请求配置中 `responseType === 'blob'`
- **THEN** get 方法 SHALL 直接返回 `response.data`，不经过 `handleResponse`
