# 在登录页增加双语切换选项

Status: ready

## Migration Context

- Legacy source: `openspec/changes/add-signin-language-toggle/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## 1. 视觉规格

胶囊 trigger 设计锚定现有登录卡片视觉风格(`SigninContentShell` + 卡片双色布局)。
截图与样式示意:

```
┌──────────────────────────────────────┐
│  🌍 简体中文 ⌄                  ◀──── 触发器(右上角绝对定位)
│
│              登录                       ◀──── 卡片标题(原有)
│          请输入账号信息继续              ◀──── 卡片副标题(原有)
│
│  用户名  [              ]               ◀──── 原有表单
│  密码    [              ]
│  [    登 录    ]
```

trigger 样式骨架:

```tsx
<button
  type="button"
  className="flex items-center gap-2 rounded-full border
             border-(--color-border-2) bg-white/85 px-3 py-2
             text-sm text-(--color-text-1) backdrop-blur
             transition-colors hover:bg-white"
>
  <GlobalOutlined className="text-base" aria-hidden />
  <span>{currentLanguageLabel}</span>
  <CaretDownOutlined className="text-xs" aria-hidden />
</button>
```

### 1.1 位置

- page mode:`SigninClient` 的右侧 login card 内,**absolute 右上**(锚到卡片右上角)
  - 桌面 ≥ md:卡片宽度 `max-w-md`,trigger `top-6 right-6`
  - 平板以下:右移右上即可,无响应式特例
- modal mode:**不在 SigninClient 中挂载**(out of scope,#1)

### 1.2 支持语言与文案

| LocaleKey | Native label | zh.json | en.json |
|---|---|---|---|
| `zh-Hans` | 简体中文 | 自指 | `English` |
| `en` | English | `简体中文` | 自指 |

Dropdown 展开后**只展示另一项**(过滤掉当前 locale),避免无意义自身条目。

## 2. 组件边界

| 组件 | 知道后端? | 知道 session? | 职责 |
|---|---|---|---|
| `SigninLanguageToggle` | ❌ | ❌ | 渲染 + 调 `useLocale().setLocale(target)` |
| `SigninClient` | 不引入 | 不引入 | 仅挂载组件,不传任何业务 prop |
| `LocaleProvider` | 不变 | 不变 | 沿用既有 `changeLocale` 实现 |

**新增文件不引入 `useEffect` / 不引入网络请求 / 不引入 try-catch**。
唯一的状态更新入口是 `useLocale().setLocale`,其内部已经处理好副作用。

## 3. 行为契约

伪代码示意(signin-only,无副作用):

```tsx
const SUPPORTED_LANGUAGES = [
  { key: 'zh-Hans', label: '简体中文' },
  { key: 'en',      label: 'English'  },
] as const;

export default function SigninLanguageToggle() {
  const { t } = useTranslation();
  const { locale, setLocale } = useLocale();

  const current = SUPPORTED_LANGUAGES.find(l => l.key === locale)
                ?? SUPPORTED_LANGUAGES[0];                       // 兜底英文

  const items = SUPPORTED_LANGUAGES
    .filter(l => l.key !== locale)
    .map(l => ({
      key: l.key,
      label: l.label,
      onClick: () => setLocale(l.key),                          // 唯一副作用
    }));

  return (
    <Dropdown menu={{ items }} trigger={['click']} placement="bottomRight">
      <button type="button"
              aria-label={t('signin.languageToggle.label')}
              /* 上面样式骨架 */
      >
        <GlobalOutlined aria-hidden />
        <span>{current.label}</span>
        <CaretDownOutlined aria-hidden />
      </button>
    </Dropdown>
  );
}
```

调用 `useLocale().setLocale(target)` 后,`LocaleProvider.changeLocale` 已经会:

1. `setLocale(target)` —— 触发 `IntlProvider` 重渲染,组件树立刻切到目标语言
2. `persistLocale(target)` —— 写 `window.localStorage['locale']`
3. `fetchLocaleMessages(target)` —— `GET /api/locales?locale=xx` 拉取新文案

本组件**不再额外做任何事**。

## 4. modal mode:沿用现有行为,不动

modal mode 触发于"已登录但 token 过期"。此时通常有以下几种状态:

| 是否有 `session.user.locale` | LocaleProvider 行为(本次仍适用) |
|---|---|
| 有 | 现有逻辑链不直接读 `session.user.locale`;若父页面未主动同步,modal 仍按 localStorage / 默认渲染 —— 这是**当前既定行为**,本次不修复 |
| 无 | 走 `DEFAULT_LOCALE = 'en'` |

即:**modal mode 现有行为已"读不到就走默认"**。本次不做开关、不加 prop、
不在 `SigninClient` 里读 `useSession()`。后续若团队发现"modal 实际未吃到
session.user.locale"问题,另开 OpenSpec 处理(可参考前一轮讨论的"登录后
locale 反向同步"裂缝,但那是独立 change,不与本次合并)。

## 5. i18n 键

`signin.languageToggle` 节,zh/en 两侧对齐:

```jsonc
// zh.json
"languageToggle": {
  "label":   "切换语言",
  "zhItem":  "简体中文",
  "enItem":  "English"
}

// en.json
"languageToggle": {
  "label":   "Switch language",
  "zhItem":  "Simplified Chinese",
  "enItem":  "English"
}
```

- `label`:trigger 的 `aria-label`,屏幕阅读器读出
- `zhItem` / `enItem`:Dropdown 菜单条目文字(简体中英 native label 双语一致,
  这里的 `*Item` 是 i18n 描述键,不是语言切换本身的 label)

## 6. 测试策略

### 6.1 回归脚本(web 仓库 `tsx scripts/*-test.ts` 风格)

> web 仓库不配置 RTL/Jest;约定回归脚本对齐
> `web/scripts/cmdb-app-overview-wiring-test.mjs` 与
> `web/scripts/cmdb-attr-type-i18n-test.ts`。
> 测试通过 `fs.readFileSync` 读源文件 + 正则断言"源代码契约",
> 不构建 React,不连真实网络。

```ts
// web/scripts/signin-language-toggle-test.ts(草案)
import * as assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const componentPath = resolve(here, '../src/app/(core)/auth/signin/login-auth/SigninLanguageToggle.tsx');
const signinClientPath = resolve(here, '../src/app/(core)/auth/signin/SigninClient.tsx');
const zhPath = resolve(here, '../src/locales/zh.json');
const enPath = resolve(here, '../src/locales/en.json');

const failures: string[] = [];

// 组件存在性 + 契约
if (!existsSync(componentPath)) {
  failures.push('缺少组件文件');
} else {
  const src = readFileSync(componentPath, 'utf8');
  if (!/SUPPORTED_LANGUAGES[\s\S]*?\.find\s*\([^]*?locale\s*\)/.test(src)) failures.push('trigger 未基于 SUPPORTED_LANGUAGES.find 解析当前');
  if (!/aria-label\s*=\s*\{\s*t\(\s*['"]signin\.languageToggle\.label['"]\s*\)\s*\}/.test(src)) failures.push('trigger 缺 aria-label i18n 键');
  if (!/SUPPORTED_LANGUAGES[\s\S]*?\.filter\s*\(\s*\(\s*lang\s*\)\s*=>\s*lang\.key\s*!==\s*locale\s*\)/.test(src)) failures.push('Dropdown 未过滤当前 locale');
  if (!/onClick:\s*\(\s*\)\s*=>\s*setLocale\(\s*lang\.key\s*\)/.test(src)) failures.push('onClick 未调 setLocale(lang.key)');
  if (/\bfetch\s*\(/.test(src)) failures.push('组件内不应有 fetch()');
  if (/\buseSession\s*\(/.test(src)) failures.push('组件内不应引入 useSession');
}

// i18n 键双侧对齐
function flatten(obj: Nested, prefix = ''): Record<string, string> { /* ... */ }
const need = ['signin.languageToggle.label', 'signin.languageToggle.zhItem', 'signin.languageToggle.enItem'];
for (const k of need) {
  if (flatten(JSON.parse(readFileSync(zhPath, 'utf8')))[k] === undefined) failures.push(`zh.json 缺 ${k}`);
  if (flatten(JSON.parse(readFileSync(enPath, 'utf8')))[k] === undefined) failures.push(`en.json 缺 ${k}`);
}

// SigninClient 接入
const sc = readFileSync(signinClientPath, 'utf8');
if (!/import\s+SigninLanguageToggle\s+from\s+['"][^'"]*login-auth\/SigninLanguageToggle['"]/.test(sc)) failures.push('SigninClient 缺 import');
if (!/<SigninLanguageToggle\s*\/\>/.test(sc)) failures.push('SigninClient 未挂载组件');
if (/if\s*\(\s*mode\s*===\s*['"]modal['"]\s*\)[\s\S]{0,400}<SigninLanguageToggle/.test(sc)) failures.push('modal mode 不该挂载组件');

// e2e:e2e/playwright 在 §6.3 另议
assert.equal(failures.length, 0, '\n失败:\n  - ' + failures.join('\n  - '));
console.log('signin language toggle test passed');
```

**测的是行为契约**(组件契约性 + i18n 键双侧对齐 + 接入点),不测 React 运行时。
    之所以这么做:web 仓没有 RTL/Jest 配置;若改造测试基建超出本次范围。

### 6.2 视觉回归

- 桌面 ≥ md:switcher 与卡片标题不重叠、不顶到卡片边缘外
- 平板宽度:switcher 仍居右上,不与表单重叠
- 暗色主题(若仓库有 dark mode 主题色,例如 `themeName === 'dark'`):
  trigger 样式需在两种 theme 下均可读

### 6.3 e2e(可选,Playwright)

- 打开 `/auth/signin` → 断言 trigger 文案 = `简体中文`(默认英文 = `English`)
  取决于默认 locale
- 点击 trigger → 菜单展开包含另一语言
- 选择目标语言 → 断言 `localStorage['locale']` 更新
- 断言登录标题"登录"切换为"Sign In"(端到端确认 IntlProvider 工作)

## 7. 风险与回滚

- **风险面极小**。本次只新增组件 + 加 i18n 键 + SigninClient 渲染树挂载,
  移除本组件即可恢复原状(单文件 revert)。
- **回归点**:`SigninClient` page mode DOM 结构变化(右上多一块浮元素),
  理论上不影响表单交互;若视觉出现问题,降级方案 = 改 absolute 偏移量或
  临时下掉 trigger 展示。
- **i18n 键漏写**:`/api/locales` 路由当前会把缺键回退到 defaultLocale
  (`en`),所以一侧写错不会立刻崩溃 —— 但应避免,commit 前对齐双侧。

## 8. 不做的清单(再次明确)

| 不做项 | 原因 |
|---|---|
| PATCH `update_user_info` | 用户明确要求"登录后不更新用户语言环境" |
| 登录请求 body `preferred_locale` | 同上,且必须改后端接口,违反"不做服务端变更" |
| `useSession()` 依赖 | modal 不加、本组件不加,引入只会膨胀 |
| 反向 `persistLocale(serverLocale)` | 同上;改动面超出本次 |
| 改 `DEFAULT_LOCALE` | 独立 change |
| Accept-Language 嗅探 | 独立 change |
| 动 `LocaleProvider.changeLocale` | 增加风险面,且本组件不需要 |
| 加 OpenSpec `specs/...` | 本次只创建 change 目录,待 sync 阶段统一归并 |

## Work Checklist

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
