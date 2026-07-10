# 修 LocaleProvider 切换语言时的整页闪烁

## Why

issue #0003:用户点击登录页双语切换器时,整页会从登录页瞬间切到 `<Spin/>`,fetch 完成后切回——视觉上"闪一下 loading"。

根因:`LocaleProvider.changeLocale` 调用 `fetchLocaleMessages`,后者内部 `setIsLoading(true)` 把整页 children 卸载换成 `<Spin/>`,fetch 完成后 `setIsLoading(false)` 重新挂载 children。详见 issue #0003 与仓库现状 `web/src/context/locale.tsx`(本 change 实施前)。

## What Changes

`web/src/context/locale.tsx` 区分两条路径:

- **初始化路径**(`useEffect` mount 后):
  显式 `setIsLoading(true)` → fetch → `.finally(() => setIsLoading(false))`,显示 `<Spin>` 占位。
- **切换路径**(`changeLocale` 用户切语言时):
  仍后台调用 `fetchLocaleMessages` 拉新 messages —— 但**不再触发 `isLoading` 状态**,children 持续渲染,react-intl 在新 messages 到达后自然 re-render 到新文案。

抽出共享 fetch 子流程,`fetchLocaleMessages` 函数体内**不再 `setIsLoading(...)`**;loading 状态完全由初始化 useEffect 显式管控。

## 为什么选 A 方案

经方案评审,A 改动最小、风险最低、不破坏 `/api/locales` 路由对 install app locales 的 merge 能力;B(预加载)会失去该能力,C(预加载+后台 merge)复杂度激增且首次加载新 key 仍 fallback。

A 的代价:切语言 fetch 完成前,新 locale 不可用的 key 会 react-intl fallback 到 `defaultMessage` 或 key 字面量;登录页常用键(`signin.form.*` / `signin.pageTitle.login` 等)在 base locales 内必命中,大多数场景无可见退化。

## 影响面

| 类别 | 内容 |
|---|---|
| 修改文件 | `web/src/context/locale.tsx` (净 diff ≈ 4 行) |
| 新增文件 | `web/scripts/locale-provider-switch-flash-test.ts` (~80 行源码契约回归) |
| **不修改** | `/api/locales` 路由、`<Spin>` 组件、`IntlProvider`、其它 locale 工具 |

## Out of Scope(本次明确不做)

- 不预加载(方案 B):失去 install app locales 合并能力,需独立 OpenSpec。
- 不改 `/api/locales` 路由。
- 不改 `<Spin>` 组件。
- 不重构 LocaleProvider 整体(本 change 只动"切语言不闪"这一最小诉求)。
