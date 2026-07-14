# Tasks — add-signin-language-toggle

## 1. TDD:写组件 + 断言脚本

> 测试风格说明:**web 仓库不配置 RTL/Jest,约定为 `tsx scripts/*-test.ts`**
> (对齐 `web/scripts/cmdb-app-overview-wiring-test.mjs` 等)。
> 因此"测试"用源代码契约断言(fs.readFileSync + 正则)而不是 React DOM 跑通。
> 这条与 design.md §6 同步。

- [ ] 1.1 在 `web/src/app/(core)/auth/signin/login-auth/SigninLanguageToggle.tsx` 创建组件源码
      + 在 `web/scripts/signin-language-toggle-test.ts` 创建 tsx 回归脚本
- [ ] 1.2 断言:trigger 渲染当前 locale 对应的 native label(基于 `SUPPORTED_LANGUAGES.find(... === locale)`)
- [ ] 1.3 断言:trigger 的 `aria-label` = `t('signin.languageToggle.label')` 的字符串字面量
- [ ] 1.4 断言:Dropdown 项渲染时 `.filter(lang => lang.key !== locale)`,不展示自身
- [ ] 1.5 断言:onClick → `setLocale(lang.key)`,且不调任何 fetch
- [ ] 1.6 断言:组件内**不引入** `fetch(`/`useSession(`/`try-catch`

## 2. i18n 键

- [ ] 2.1 在 `web/src/locales/zh.json` 的 `signin.languageToggle` 下加 `label` / `zhItem` / `enItem`
- [ ] 2.2 在 `web/src/locales/en.json` 的 `signin.languageToggle` 下加 `label` / `zhItem` / `enItem`
- [ ] 2.3 diff 校对:zh/en 两侧结构对齐,均无多余字段

## 3. 实现组件

- [ ] 3.1 `SigninLanguageToggle.tsx`:antd `Dropdown` + trigger 按钮 + 单文件 ~30 行
- [ ] 3.2 `SUPPORTED_LANGUAGES` 常量与 native label 锁在文件内(本次不引入新 constants 文件)
- [ ] 3.3 不引入 try-catch、不引入 fetch、不引入 useSession

## 4. 接入到 SigninClient

- [ ] 4.1 `SigninClient.tsx` 在 page mode 渲染树中,在标题区右上角挂载 `<SigninLanguageToggle />`
- [ ] 4.2 modal mode 渲染树不变(本次明确 out of scope)
- [ ] 4.3 import 收敛到 page mode 分支内,modal 分支不引入新 import

## 5. 门禁

- [ ] 5.1 `cd web && pnpm lint` 全过
- [ ] 5.2 `cd web && pnpm type-check` 全过
- [ ] 5.3 受影响单测全绿

## 6. 视觉回归(可选,但建议)

- [ ] 6.1 桌面 ≥ md 下 trigger 与卡片标题不重叠
- [ ] 6.2 平板宽度下 trigger 与表单不重叠
- [ ] 6.3 暗色主题(若存在)trigger 仍可读
- [ ] 6.4 截图存 `openspec/changes/add-signin-language-toggle/review/page-mode.png`

## 7. e2e(可选,Playwright)

- [ ] 7.1 访问 `/auth/signin` 断言 trigger 文案
- [ ] 7.2 点击展开 → 点击目标语言 → 断言 `localStorage['locale']` 已更新
- [ ] 7.3 断言页面标题"登录"切换为"Sign In"(或反向)
- [ ] 7.4 e2e 不发起 `update_user_info` 任何请求

## 8. 反向同步用例(不在本次)

不引入任何 login-callback 阶段的 `persistLocale(serverLocale)` 调用;
不引入登录请求 body 的 `preferred_locale` 字段。
