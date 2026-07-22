# 修 LocaleProvider 切换语言时的整页闪烁

Status: ready

## Migration Context

- Legacy source: `openspec/changes/fix-locale-provider-switch-flash/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

按 pjm 的 issue 评审,A 改动最小、风险最低、不破坏 `/api/locales` 路由对 install app locales 的 merge 能力;B(预加载)会失去该能力,C(预加载+后台 merge)复杂度激增且首次加载新 key 仍 fallback。

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

## Implementation Decisions

## 1. 状态机改造前后

### 改造前

```
mount(useEffect)
  ├─ setLocale(savedLocale)
  └─ fetchLocaleMessages(savedLocale)
        ├─ setIsLoading(true)            ← 把 children 卸载换 <Spin/>
        ├─ await fetch /api/locales
        └─ setIsLoading(false)            ← children 重挂载

changeLocale (用户切语言时)
  ├─ setLocale(newLocale)
  ├─ persistLocale(newLocale)
  └─ fetchLocaleMessages(newLocale)
        ├─ setIsLoading(true)            ← ✗ 同样卸载 children
        ├─ await fetch /api/locales
        └─ setIsLoading(false)
```

### 改造后

```
mount(useEffect)
  ├─ setLocale(savedLocale)
  ├─ setIsLoading(true)                   ← 初始化路径显式开 loading
  ├─ fetchLocaleMessages(savedLocale)     (函数内不再 setIsLoading)
  │     ├─ await fetch /api/locales
  │     ├─ setMessages(data)
  │     └─ (失败 console.error,不抛)
  └─ .finally(() => setIsLoading(false))

changeLocale (用户切语言时)
  ├─ setLocale(newLocale)
  ├─ persistLocale(newLocale)
  └─ void fetchLocaleMessages(newLocale)   (函数内不再 setIsLoading → 不闪)
        ├─ await fetch /api/locales
        ├─ setMessages(data)
        └─ (失败 console.error)
```

## 2. 关键改动点(精确 diff ≈ 4 行)

`fetchLocaleMessages` 函数体内**删除**这两处:
- `setIsLoading(true);`(位于 try 之前)
- `finally { setIsLoading(false); }`(整个 finally 块)

`useEffect` 内**补充**以下成对调用:
- 在 `fetchLocaleMessages(savedLocale)` 之前加 `setIsLoading(true);`
- 在 `fetchLocaleMessages(savedLocale)` 之后接 `.finally(() => setIsLoading(false))`

`changeLocale` 不动;它仍调用 `fetchLocaleMessages`,但由于后者不再设 loading 状态,不再触发 `<Spin>`。

## 3. 用户体验

| 切语言时机 | 改造前 | 改造后 |
|---|---|---|
| 瞬间(0 - fetch 完成) | `<Spin/>` 占位(白屏 + 加载圈),children 卸载 | children 持续渲染,UI 维持,**无闪** |
| fetch 完成后 | children 重挂载,文案切换 | `messages` 更新,`<IntlProvider>` 内部 re-render,文案切换(无组件卸载) |

短暂 fallback 仍可能存在(react-intl 在 key 缺失时),但登录页 `signin.*` 核心键都在 base locales 内,概率极低。

## 4. 测试策略

`web/scripts/locale-provider-switch-flash-test.ts`,沿用仓库 `tsx scripts/*-test.ts` 约定,断言源码契约:

```ts
// 1. fetchLocaleMessages 函数体内**不应**存在 setIsLoading(
//    (loading 完全由 init 路径管控)
const fetchFnBlock = src.match(...)
if (/\bsetIsLoading\s*\(/.test(fetchFnBlock[0])) {
  failures.push('[locale.tsx] fetchLocaleMessages 内不应调 setIsLoading')
}

// 2. useEffect 初始化路径**必须**有 setIsLoading(true) 与 finally setIsLoading(false)
if (!/\bsetIsLoading\s*\(\s*true\s*\)/.test(useEffectBlock[0])) {
  failures.push('[locale.tsx] useEffect 必须 setIsLoading(true)')
}
if (!/finally\s*\(\s*\(\s*\)\s*=>\s*setIsLoading\s*\(\s*false\s*\)/.test(useEffectBlock[0])) {
  failures.push('[locale.tsx] useEffect 必须在 fetch 后 finally 关 setIsLoading')
}

// 3. changeLocale 内仍必须调 fetchLocaleMessages (后台拉新 messages)
if (!/\bfetchLocaleMessages\s*\(/.test(changeFnBlock[0])) {
  failures.push('[locale.tsx] changeLocale 必须调 fetchLocaleMessages')
}
```

测的是行为契约(loading 与 fetch 解耦 + 切换仍 fetch),不测 React 运行时。

## 5. 风险

- **react-intl fallback**:fetch 命中失败 / 跨域网络抖动下 children 短暂显示 id 字面量或 defaultMessage。已在 `useTranslation` 加 `console.error` 兜底,不会出现崩溃白屏。
- **初始化路径双重 isLoading**:理论上 useEffect 显式 + fetchLocaleMessages 内部两路会冲突,本设计通过"fetchLocaleMessages 函数体内删除 setIsLoading"消除。
- **回滚成本**:diff ≈ 4 行,可在任意 git 节点 revert。

## 6. 不做的事(再次明确)

- 不预加载(方案 B):失去 install app locales merge 能力
- 不改 `/api/locales` 路由
- 不动 `<Spin>` 组件
- 不动 `IntlProvider`

## Work Checklist

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
