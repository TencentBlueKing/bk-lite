# Design — 修切语言闪烁(方案 A)

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
