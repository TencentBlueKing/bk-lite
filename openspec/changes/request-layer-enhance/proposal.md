## Summary

优化 `web/src/utils/request.ts` 的请求封装层，解决拦截器重复注册、HTTP 方法无意义 try/catch、handleResponse 混合副作用三个核心问题，并新增声明式 useRequest hook。

## Capabilities

### interceptor-singleton
将 request/response 拦截器从 `useApiClient` 的 `useEffect` 移至模块级别，只注册一次。Token 通过 `setToken()` 函数注入，从模块级 `tokenRef` 读取。

### method-simplify
移除 5 个 HTTP 方法的无意义 `try { ... } catch { throw error }` 包装和 `onError` 参数。`handleResponse` 去掉 `message.error` 副作用，只做数据解析。

### use-request-hook
新增 `useRequest` hook，提供 auto/manual 两种模式、loading/error/data 状态管理、AbortController 请求取消、refreshDeps 依赖刷新、StrictMode 安全的卸载取消。

## Motivation

- 145 个文件 292 处使用 `useApiClient`，每次挂载都注册/eject 拦截器 → 性能浪费 + 潜在竞态
- try/catch 只是 re-throw → 纯噪音
- handleResponse 混合数据提取和 UI 弹窗 → 不可测试、不可复用
- 无请求取消 → 页面切换后仍处理过期响应

## Impact

- `useApiClient` 返回接口 `{ get, post, put, del, patch, isLoading }` 不变，145 个消费文件零改动
- `handleResponse` 不再弹 `message.error`，但 response 拦截器的 400/500 分支已有弹窗，影响可控
- `onError` 参数移除（全局搜索确认 0 处实际使用）
- useRequest 为 opt-in，不强制迁移
