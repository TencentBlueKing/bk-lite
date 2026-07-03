# 登录链路双语支持设计

## 背景

主控制台已经有全局国际化能力：`LocaleProvider` 通过 `/api/locales` 加载并合并 `web/src/locales/en.json` 与 `web/src/locales/zh.json`，业务组件通过 `useTranslation()` 获取文案。当前登录链路没有接入这套机制，`SigninClient`、`PasswordResetForm`、`OtpVerificationForm` 中存在硬编码英文，`WechatQrLoginPanel` 中存在硬编码中文，导致切换语言后登录页展示不一致。

## 目标

- 覆盖 `/auth/signin` 主登录页与登录弹窗模式。
- 覆盖密码重置、OTP 校验、微信扫码登录面板、第三方登录按钮、NextAuth 登录错误提示。
- 复用现有 `useTranslation()` 与全局 locale 文件，不引入第二套翻译机制。
- 仅翻译前端本地兜底文案；后端接口返回的 `responseData.message` 暂时原样展示。

## 非目标

- 不调整登录页视觉布局和交互流程。
- 不治理后端错误消息的多语言。
- 不新增语言种类。
- 不改造 `/api/locales` 合并策略。

## 方案

采用全局 locale 方案，在 `web/src/locales/en.json` 与 `web/src/locales/zh.json` 增加 `signin` 命名空间。登录链路组件统一调用 `useTranslation()`，所有用户可见的本地静态文案与兜底错误文案改为 `t('signin.form.username')` 这类明确 key。

### 组件改造

- `SigninClient`
  - 引入 `useTranslation()`。
  - 表单标签、placeholder、按钮、加载态、第三方登录分隔文案、微信浏览器提示、页面标题与描述统一改为翻译 key。
  - 弹窗无法打开、登录失败、认证失败、微信不可用等前端兜底错误改为翻译 key。
  - 将 `signinErrors` 从“错误码到英文文案”调整为“错误码到翻译 key”，由客户端渲染时调用 `t()`。

- `PasswordResetForm`
  - 引入 `useTranslation()`。
  - 标题、说明、字段标签、placeholder、提交按钮、前端校验错误与兜底错误改为翻译 key。

- `OtpVerificationForm`
  - 引入 `useTranslation()`。
  - 标题、说明、绑定步骤、字段标签、placeholder、按钮加载态、前端校验错误与兜底错误改为翻译 key。
  - `alt` 文案使用翻译 key。

- `WechatQrLoginPanel`
  - 引入 `useTranslation()`。
  - 微信配置不可用、配置获取失败、二维码加载失败、加载中、无法显示二维码等文案改为翻译 key。

### Locale 结构

新增 `signin` 命名空间，建议按页面区域组织：

- `signin.errors.*`
- `signin.form.*`
- `signin.passwordReset.*`
- `signin.otp.*`
- `signin.thirdParty.*`
- `signin.wechatQr.*`
- `signin.pageTitle.*`
- `signin.pageDescription.*`

命名空间放在全局 locale 文件中，原因是登录链路属于 `(core)`，不是独立应用目录；沿用全局文件可以避免扩展 `/api/locales` 的扫描规则。

## 数据流

1. `LocaleProvider` 读取本地保存语言并请求 `/api/locales?locale=...`。
2. `/api/locales` 返回展平后的全局消息。
3. 登录组件通过 `useTranslation()` 读取 `signin.*` key。
4. 用户登录成功后，现有认证流程继续保存后端返回的用户语言偏好，不改变重定向逻辑。

## 错误处理

- 前端主动产生的错误使用翻译文案。
- 后端返回的 `responseData.message` 保持优先展示，避免误翻译后端真实错误信息。
- 当翻译 key 缺失时，现有 `useTranslation()` 会返回 default message 或 key；实现时应为新增调用提供清晰 key，并同步补齐中英文 locale。

## 测试与验证

- 执行 `cd web && pnpm lint && pnpm type-check`。
- 静态检查登录目录剩余明显用户可见硬编码文案，重点排除日志、协议常量、CSS class、接口字段。
- 手动验证语言为中文和英文时：
  - 登录表单文案随语言切换。
  - 第三方登录区域文案随语言切换。
  - 密码重置与 OTP 页面文案随语言切换。
  - 微信扫码面板中文硬编码消失。

## 风险

- 登录页处于认证入口，任何 hook 使用都必须保持在 `LocaleProvider` 下运行。当前 `web/src/app/layout.tsx` 已包裹 `LocaleProvider`，风险较低。
- `signinErrors` 从服务端传入客户端，若直接传函数不可行；应传纯 key 映射并在客户端翻译。
- 后端错误仍可能出现单语言，这是本次明确不覆盖的边界。
