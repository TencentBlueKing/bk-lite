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
