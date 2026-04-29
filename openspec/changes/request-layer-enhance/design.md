## Context

当前 `request.ts` 的 `useApiClient` hook 结构：
- 模块级 `apiClient = axios.create(...)` 单例
- hook 内 `useEffect` 注册 request/response 拦截器（每个消费者都注册一次）
- 5 个 HTTP 方法（get/post/put/del/patch），每个都是 `try { await apiClient.xxx(); handleResponse() } catch { throw error }`
- `handleResponse` 解析 `{ result, message, data }` + 弹 `message.error` + 调 `onError` 回调

消费模式：57 个 api hook 文件 + 88 个页面/组件直接调用，共 145 个文件 292 处使用。

## Goals / Non-Goals

**Goals:**
- 拦截器只注册一次，消除组件挂载/卸载导致的重复注册
- HTTP 方法去掉无意义的 try/catch 包装
- handleResponse 变成纯数据提取，不再有 UI 副作用
- 新增 useRequest hook 支持声明式请求（loading/error/cancel）
- **useApiClient 返回接口不变**，145 个文件零改动

**Non-Goals:**
- 不改动现有 57 个 api hook 文件的函数签名
- 不强制现有页面迁移到 useRequest（opt-in，新代码推荐使用）
- 不做请求缓存/去重（SWR/React Query 的领域）

## Decisions

1. **拦截器移到模块级别，token 通过 `setToken` 函数注入**
   - `useApiClient` 首次挂载时调用 `setToken(token)` 更新模块级 `tokenRef`
   - request 拦截器在模块加载时注册一次，从 `tokenRef.current` 读取 token
   - 移除 `useEffect` 中的 `interceptors.request.use / eject` 逻辑

2. **业务错误提示统一到 response 拦截器**
   - `handleResponse` 只做 `{ result, data, message }` 解析：`result === false` 时 `throw new Error(msg)`
   - 移除 `handleResponse` 中的 `message.error()` 调用和 `onError` 参数
   - response 拦截器的 400/500 分支已经有 `message.error`，无需重复

3. **HTTP 方法直接 return，不 try/catch**
   ```ts
   const get = useCallback(async <T>(url, config) => {
     const response = await apiClient.get<T>(url, config);
     return config?.responseType === 'blob' ? response.data : handleResponse(response);
   }, []);
   ```

4. **useRequest hook 设计**
   - 两种模式：auto（挂载即发请求）、manual（调用 run 才发）
   - `refreshDeps` 依赖变化时重新发请求，自动取消上一次
   - 组件卸载时取消进行中的请求（AbortController + setTimeout(0) 防 StrictMode）
   - `onSuccess` / `onError` 回调

## Risks / Trade-offs

- [handleResponse 行为变化] 移除 `message.error` 后，`result === false` 的错误不再自动弹提示 → 业务层需要在 catch 中自行弹提示。但现有 api hook 的调用方几乎都有自己的 try/catch + message.error，影响可控
- [onError 参数移除] 全局搜索确认 `onError` 回调实际使用量为 0 处（声明了但没传），安全移除
