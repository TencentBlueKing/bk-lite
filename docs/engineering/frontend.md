# 前端工程规则

> 前端(web / mobile / webchat)工程约定。视觉 token 的唯一真相源是 [Web Design](../../web/DESIGN.md)；本文不复制具体颜色值。

## 1. 技术栈

| 端 | 栈 | 包管理 | Node |
|----|----|--------|------|
| `web/` | Next.js 16 / React 19 / TS / Ant Design / Tailwind / App Router | **pnpm**(`only-allow` 强制) | 24(`web/.nvmrc`) |
| `mobile/` | Next.js 15 / Tauri 2(Rust) | pnpm | — |
| `webchat/` | npm monorepo(core/ui/demo) | **npm** | ≥18 |

## 2. 硬性约定

- **包管理器不可混用**:web/mobile 用 pnpm(npm/yarn 被 `preinstall` 拦截),webchat 用 npm。
- TypeScript:接口用 `interface`,**禁用 `any`**,不可信值用 `unknown`。
- i18n:web 用 `react-intl`;新增文案走 i18n,不硬编码中文字符串到组件。
- 鉴权:web 用 `next-auth`;API 经 `NEXTAPI_URL` / `/api/proxy/*` 转发到 server。

## 3. 视觉与组件(引用 web/DESIGN.md)

- 颜色、圆角、间距、排版、组件样式必须取自 `web/DESIGN.md` 的现行 token，禁止复制本文中的历史示例值。
- 卡片、按钮、链接等基础组件遵循 `web/DESIGN.md` 与 `web/COMPONENT_GOVERNANCE.md`。
- 产品侧 UI 规范见 [`legacy-design-ui`](../../specs/capabilities/legacy-design-ui.md)。

## 4. 提交前门禁

```bash
cd web    && pnpm lint && pnpm type-check    # web
cd mobile && pnpm lint && pnpm type-check    # mobile
cd webchat && npm run build && npm run test  # webchat
```
`.husky/pre-commit` 会对 web/mobile 的 staged 变更自动执行上述检查。

## 5. 常见坑

- `pnpm install` 被拒 → 你在 web/mobile 用了非 pnpm。
- `next build` 内存不足 → 参考 `web/Dockerfile` 的 `NODE_OPTIONS`,本地降并发。
- `mobile dev:tauri` 连不上后端 → 确认 `src-tauri/tauri.conf.json` 的 `devUrl=3001` 且后端可达。
- Storybook:`pnpm storybook`(:6006)。

## 6. 前端验收清单(发版/重要页面前自检)

> 发版或重要页面前的前端验收维度,结合 `web/DESIGN.md` token 一起用。

| 维度 | 本项目关注点 |
|------|-------------|
| HTML / 语义 | 语义标签、表单 label、文档结构正确 |
| CSS / 响应式 | 取 `web/DESIGN.md` token,响应式断点,无硬编码色值 |
| JavaScript | 无 `any`(用 `unknown`)、异步错误有处理、无 console 残留 |
| 性能 | 首屏/Core Web Vitals、按需加载、图片优化、避免大包 |
| 可访问性(a11y) | 键盘可达、ARIA、对比度、焦点可见 —— 原清单此类最多(95 条) |
| SEO | title/meta、语义结构(管理后台权重低,门户/portal 高) |
| 安全 | 不可信输入转义、无敏感信息进前端、CSP/外链 `rel` |
| 图片 | 尺寸/格式/懒加载、alt 文本 |
| i18n | 文案走 `react-intl`,无硬编码中文,时区/本地化 |
| 测试 | 关键交互有覆盖,`pnpm lint && type-check` 通过 |
| 隐私 | 不超采集、第三方脚本可控 |

> 这些维度同时用于 web/mobile 改动前的技术债自检。

---

> 完整工作流见 [Agent Guide](../../AGENTS.md)；质量红线见 [质量门禁](../governance/quality.md)。
