# Tasks — fix-locale-provider-switch-flash

## 1. TDD:写回归脚本(red 阶段)

- [ ] 1.1 在 `web/scripts/locale-provider-switch-flash-test.ts` 创建 tsx 回归脚本
- [ ] 1.2 断言:`fetchLocaleMessages` 函数体内**不存在** `setIsLoading(`
- [ ] 1.3 断言:useEffect 初始化路径**必须**有 `setIsLoading(true)`
- [ ] 1.4 断言:useEffect 初始化路径**必须**有 `finally(() => setIsLoading(false))`
- [ ] 1.5 断言:`changeLocale` 内**仍调用** `fetchLocaleMessages(...)`(后台拉新 messages)

> TDD red 跑这些断言:**应当先 fail** —— 当前 LocaleProvider 实现下,
> 1.2 / 1.3 至少一条不满足。

## 2. 实施 LocaleProvider 改造(green 阶段)

- [ ] 2.1 在 `fetchLocaleMessages` 函数体内删除 `setIsLoading(true);` 与 `finally { setIsLoading(false); }` 两处
- [ ] 2.2 在 useEffect 的 `fetchLocaleMessages(savedLocale)` 调用前加 `setIsLoading(true);`
- [ ] 2.3 在 useEffect 的 `fetchLocaleMessages(savedLocale)` 调用后接 `.finally(() => setIsLoading(false))`
- [ ] 2.4 净 diff ≤ 4 行(strict 最小化)

## 3. 跑门禁

- [ ] 3.1 `cd web && pnpm tsx scripts/locale-provider-switch-flash-test.ts` 通过(red → green)
- [ ] 3.2 `cd web && pnpm tsx scripts/signin-language-toggle-test.ts` 仍通过(回归)
- [ ] 3.3 `cd web && pnpm lint` 对修改文件 0 错

## 4. 浏览器自验(非 TDD)

- [ ] 4.1 刷新 `/auth/signin`,点切换器 —— 整页**不再**出现 `<Spin/>` 占位
- [ ] 4.2 切换 ~100ms 后整页文案切到目标语言
- [ ] 4.3 切完不刷新,刷新页面,语言保留(localStorage 持久化)

## 5. 不做(明确)

- 不预加载(那是方案 B 的事)
- 不改 `/api/locales`
- 不动 `<Spin>` 组件
