# 在登录页增加双语切换选项

## Why

登录页(`web/src/app/(core)/auth/signin/`)当前没有给用户提供任何语言切换能力。
语言环境只在 `LocaleProvider`(详见 `web/src/context/locale.tsx`)里被管理,
且初始化完全依赖 `localStorage.locale` + `DEFAULT_LOCALE = 'en'`(详见
`web/src/utils/userPreferences.ts:1`)。未登录访客即便浏览器是中文,首屏也只能看到英文。

本次只解决一件事:**让未登录访客和老用户在登录页内可以临时切换中英文**。
明确不做用户语言偏好与账户语言的耦合 —— 登录后用户的语言环境以服务端
`User.locale`(`session.user.locale`)为准,登录页切换器不持久化到后端、
也不影响现有登录流程。

## What Changes

- 新增组件 `web/src/app/(core)/auth/signin/login-auth/SigninLanguageToggle.tsx`:
  antd `Dropdown` 形态,胶囊 trigger(地球 icon + 当前语言 native label + 下拉箭头),
  展开菜单条目为目标语言。点击 → `useLocale().setLocale(target)`。
- `useLocale().setLocale()` 已存在的副作用(更新 state + 写 localStorage +
  重新 fetch `/api/locales?locale=xx`)即满足本次需求,**不引入任何新副作用**。
- 在 `SigninClient` 的 `mode === 'page'` 分支渲染树右上角挂载本组件。
- 新增 i18n 键 `signin.languageToggle.{label, zhItem, enItem}`,在
  `web/src/locales/zh.json` 与 `web/src/locales/en.json` 双侧对齐写入。

## 影响面

| 类别 | 内容 |
|---|---|
| 新增文件 | `web/src/app/(core)/auth/signin/login-auth/SigninLanguageToggle.tsx` |
| 修改文件 | `web/src/app/(core)/auth/signin/SigninClient.tsx`(仅 page mode 渲染树挂载) |
| 修改文件 | `web/src/locales/zh.json`、`web/src/locales/en.json`(新增三个键) |
| **不修改** | `web/src/context/locale.tsx`、`web/src/utils/userPreferences.ts`、`web/src/app/(core)/api/locales/route.ts`、登录请求 / 回调链路、`syncAuthenticatedSession` 等 |

## Out of Scope(本次明确不做)

1. **modal mode 不挂载本组件**。`mode === 'modal'` 时 SigninClient 不引入新 UI;
   modal 触发的"登录过期"场景一般携带 `session.user.locale`,现有 `LocaleProvider`
   在读到用户语言环境时自然就用,读不到走默认行为 —— 此行为**已存在**,
   不需要在本次变更里改造。
2. **不修改 `DEFAULT_LOCALE`**。沿用 `'en'`(首次访客英文)。
3. **不调任何后端 API**。不 PATCH `update_user_info`、不在登录请求 body 加
   `preferred_locale` 字段、不在登录响应里反向 `persistLocale`。
4. **不修改 `LocaleProvider.changeLocale` 内部行为**,也即不增加 `updateUserInfo`
   之类的副作用 —— 这是组件层面的纯表现层改动。
5. **不做 Accept-Language header 嗅探**。
6. **不修改 antd `ConfigProvider` locale 数据源**。
7. **不引入新的 OpenSpec specs**(本次不开 `specs/<capability>/spec.md`);
   等类似功能稳定后由 sync 阶段统一归并。
