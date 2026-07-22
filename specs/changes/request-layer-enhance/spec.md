# Request Layer Enhance

Status: done

## Migration Context

- Legacy source: `openspec/changes/request-layer-enhance/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-23
```

## Capability Deltas

### request-interceptor-singleton

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

### request-method-simplify

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

### use-request-hook

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

## Work Checklist

## 1. 拦截器单例化

- [x] 1.1 将 request 拦截器从 `useEffect` 移至模块顶层，在 `axios.create()` 之后立即注册；从 `tokenRef.current` 读取 token，保留 `isSessionExpiredState` 检查逻辑
- [x] 1.2 将 response 拦截器从 `useEffect` 移至模块顶层，保留 401/460/400/403/500 分支的现有错误处理逻辑
- [x] 1.3 新增模块级 `tokenRef = { current: null }` 和 `setToken(t)` 函数；`useApiClient` 中用 `useEffect` 调用 `setToken(token)` 替代之前的拦截器注册/eject 逻辑
- [x] 1.4 移除 `useEffect` 中的 `interceptors.request.eject / response.eject` 清理代码

## 2. HTTP 方法与 handleResponse 简化

- [x] 2.1 移除 `handleResponse` 的 `onError` 参数和 `message.error(msg)` 调用，使其只做 `{ result, data, message }` 解析——`result === false` 时 `throw new Error(msg)`
- [x] 2.2 移除 get/post/put/del/patch 方法的 `onError` 参数
- [x] 2.3 去掉 5 个 HTTP 方法中的 `try/catch` 包装，改为直接 `return handleResponse(await apiClient.xxx(...))`；get 保留 `responseType === 'blob'` 的 `return response.data` 分支
- [x] 2.4 移除 `import { message } from 'antd'` 和 `import { useTranslation } from '@/utils/i18n'`（response 拦截器已移至模块级，不再依赖 hook 中的 `t`）

## 3. response 拦截器补充翻译

- [x] 3.1 response 拦截器中 `t('common.serverError')` 的调用已移出 hook 上下文，需改为硬编码或从 i18n 模块直接读取；评估影响后选择方案并实施

## 4. useRequest hook

- [x] 4.1 在 `web/src/hooks/` 下新建 `useRequest.ts`，实现 auto/manual 两种模式、loading/error/data 状态管理、AbortController 请求取消
- [x] 4.2 实现 `refreshDeps` 依赖变化时自动重新发请求并取消上一次请求的逻辑
- [x] 4.3 实现 StrictMode 安全的卸载取消：cleanup 中 `setTimeout(0)` 设置 abort 延迟，re-mount 时 `clearTimeout` 取消延迟
- [x] 4.4 导出 `useRequest` 并在 `web/src/hooks/index.ts`（如存在）中 re-export

## 5. 验证

- [x] 5.1 执行 `pnpm type-check` 确认类型无误
- [x] 5.2 执行 `pnpm lint` 确认代码风格通过
- [x] 5.3 执行 `pnpm build` 确认构建成功
