# Web 系统主题模块重设计

## 背景

BK-Lite Control Console 已支持 Light/Dark，但主题能力分散在以下位置：

- `web/src/context/theme.tsx` 同时负责主题状态、DOM class、localStorage、Ant Design 和 locale/dayjs locale。
- `web/src/constants/theme.ts` 单独维护 Ant Design Light/Dark 配置。
- `web/src/styles/globals.css` 手工维护 `:root` 与 `.dark` 两套 CSS Variables。
- 部分业务代码直接读取 `localStorage.theme` 或判断 DOM 是否包含 `.dark`。
- 主题切换入口存在近似重复实现。
- 图表、拓扑和 Canvas 等非 CSS 场景各自判断模式或维护颜色。

后续产品将支持系统管理员设计并发布系统主题。管理员配置的主题需要同时包含独立的 Light/Dark 配色；普通用户不能编辑或选择主题，但仍可在当前系统主题下切换 Light/Dark。为避免后续功能继续建立在分散实现之上，本次先重构 Web 内部主题模块。

## 目标

1. 建立一个 Web 内部深模块，以小接口隐藏主题解析、存储、DOM 应用和框架适配。
2. 由同一份语义颜色 Token 同时驱动 BK-Lite CSS、Ant Design 和非 CSS 消费者。
3. 保持现有 Light/Dark 视觉与用户行为不变。
4. 首帧绘制前确定 Light/Dark，不出现默认主题闪烁。
5. 为未来管理员主题的差异覆盖、契约版本、发布快照和安全回退建立稳定模型。
6. 收口业务代码的主题依赖，防止新的直接存储和 DOM 判断。

## 非目标

- 不修改 Server，不创建主题数据表、管理接口或发布接口。
- 不实现管理员主题编辑器、隔离预览、发布、版本历史或回滚。
- 不允许配置字体、字号、圆角、间距、阴影、动效和组件尺寸。
- 不抽成 mobile、webchat 或 workspace 共享 package。
- 不在本次一次性清除全 Web 的历史硬编码颜色。
- 不改变现有颜色、主题开关位置或 Ant Design algorithm。

## 已确认的产品边界

- 系统管理员负责创建、编辑、预览和发布系统主题。
- 系统同一时间只有一个当前发布主题。
- 普通用户不能创建、编辑或选择主题。
- 每个系统主题包含独立的 Light/Dark 配色。
- 普通用户可以在当前系统主题下切换 `light | dark`。
- 管理员配置受控的 BK-Lite 语义颜色，不直接配置 Ant Design 内部 CSS Variables。
- 同一份语义颜色必须同时覆盖自研界面与 Ant Design。
- 自定义主题保存相对默认主题的差异，未配置值继承当前版本默认主题。
- 发布时解析并校验完整快照；关键对比度不合格时阻止发布。
- 已发布快照不可变，支持历史版本与指针回滚。
- 发布后不强制正在使用的页面实时换肤，新页面加载或刷新后生效。

## 总体设计

在 `web/src/theme/` 建立主题模块：

```text
web/src/theme/
├── contract.ts
├── defaults.ts
├── resolve.ts
├── css-adapter.ts
├── antd-adapter.ts
├── mode-storage.ts
├── bootstrap.tsx
├── provider.tsx
└── index.ts
```

模块职责如下：

| 文件 | 职责 |
| --- | --- |
| `contract.ts` | 定义模式、语义颜色、主题定义、完整运行时主题和元数据 |
| `defaults.ts` | BK-Lite 默认 Light/Dark 完整颜色的唯一事实源 |
| `resolve.ts` | 合并默认值与覆盖项，生成完整且类型安全的运行时主题 |
| `css-adapter.ts` | 将完整 Token 映射为新 CSS Variables 和旧变量兼容别名 |
| `antd-adapter.ts` | 将完整 Token 映射为 Ant Design 官方 `ThemeConfig` |
| `mode-storage.ts` | 唯一负责读取和写入现有 `localStorage.theme` |
| `bootstrap.tsx` | 服务端输出主题变量与首帧前模式初始化 |
| `provider.tsx` | React 状态、AntD 主题应用和消费 Hook |
| `index.ts` | 主题模块唯一公共出口 |

locale 与 dayjs locale 不属于主题职责，应从现有 ThemeProvider 移出。主题模块不得反向依赖业务 app。

## 主题契约

```ts
type ThemeMode = 'light' | 'dark';

interface ThemeMetadata {
  themeId: string;
  themeVersion: string;
  schemaVersion: number;
}

interface ThemeDefinition extends ThemeMetadata {
  light: Partial<SemanticColorTokens>;
  dark: Partial<SemanticColorTokens>;
}

interface ResolvedTheme extends ThemeMetadata {
  light: SemanticColorTokens;
  dark: SemanticColorTokens;
}
```

本次只有内置主题：

```ts
const defaultTheme: ResolvedTheme = {
  themeId: 'bklite-default',
  themeVersion: '1',
  schemaVersion: 1,
  light: completeLightTokens,
  dark: completeDarkTokens,
};
```

当前内置默认主题必须完整定义 Light/Dark。未来管理员主题使用 `ThemeDefinition` 保存差异覆盖项：

```text
当前版本默认完整 Token
          +
管理员 Light/Dark 覆盖项
          ↓
发布时完整主题快照
```

运行时和业务消费者只接触完整 Token，不处理缺失字段、继承、版本迁移或异常回退。

## 语义颜色契约

规范 Token 必须描述用途，不以 `bg-1`、`fill-3` 等编号作为未来公共契约。建议按以下能力组织，最终字段清单应以当前 `globals.css` 的稳定语义全量盘点为准：

```ts
interface SemanticColorTokens {
  interactionPrimary: string;
  interactionPrimaryHover: string;
  interactionPrimaryActive: string;
  interactionPrimarySoft: string;
  focusRing: string;

  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  textDisabled: string;

  surfacePage: string;
  surfaceContainer: string;
  surfaceElevated: string;
  surfaceMuted: string;

  borderDefault: string;
  borderSubtle: string;
  borderStrong: string;

  statusSuccess: string;
  statusWarning: string;
  statusError: string;
  statusInfo: string;

  navigationBackground: string;
  navigationText: string;
  navigationItemHoverBackground: string;
  navigationItemActiveBackground: string;
  navigationItemActiveText: string;
}
```

第一期管理员主题只开放颜色。主色相关 hover、active、focus 和弱背景可由系统生成合理默认值，同时允许管理员在高级设置中逐项覆盖；发布快照保存最终完整结果。

## 单一事实源与 CSS 兼容

默认主题的完整 Light/Dark Token 定义在 TypeScript。`globals.css` 不再手工维护两套主题颜色真值，只保留基础结构样式和变量消费。

`css-adapter.ts` 同时输出规范变量和旧变量别名：

```css
--theme-color-text-primary: <resolved value>;
--color-text-1: var(--theme-color-text-primary);
```

迁移规则：

- 新代码只使用规范 `--theme-*` 变量或主题 Hook。
- 旧页面可继续消费现有 `--color-*` 变量。
- 旧变量存在真实消费者时不得删除。
- 旧变量标记为 deprecated，并按业务模块渐进迁移。
- 旧编号变量不进入未来管理员可配置契约。

这种兼容层保证本次无需做全 Web 视觉重写，同时让未来配置契约不受历史命名限制。

## Ant Design Adapter

管理员和业务代码均不接触 `--ant-*` 或 Ant Design 内部实现变量。主题模块提供：

```ts
function createAntdTheme(
  mode: ThemeMode,
  tokens: SemanticColorTokens,
): ThemeConfig;
```

适配器负责：

- 映射品牌色、文本、背景、边框和状态色等全局公开 Token。
- 映射 Menu、Table 等确有需求的组件级公开 Token。
- Light 使用 `theme.defaultAlgorithm`。
- Dark 使用 `theme.darkAlgorithm`。
- 使用解析后的语义 Token 覆盖 algorithm 结果。

Ant Design 升级时只修改该 Adapter。数据库中的未来主题定义不保存 AntD 字段，因此不随 AntD 内部变化迁移。

## React 接口

普通页面与主题切换入口使用：

```ts
useThemeMode(): {
  mode: ThemeMode;
  setMode(mode: ThemeMode): void;
  toggleMode(): void;
}
```

图表、拓扑、Canvas 和第三方控件等不能直接消费 CSS Variables 的场景使用：

```ts
useThemeTokens(): SemanticColorTokens;
```

主题元数据只供根壳和未来诊断场景读取，不塞入普通业务接口。

模块不再公开：

- Ant Design `ThemeConfig`
- boolean 形式的 `setTheme`
- localStorage 键名
- DOM `.dark` 操作
- `lightTheme` / `darkTheme` 实现

## 首屏初始化与模式切换

### 当前阶段

```text
内置默认 ThemeDefinition
        ↓
服务端解析完整 Light/Dark Token
        ↓
<head> 输出两套 CSS Variables
        ↓
首帧前脚本读取 localStorage.theme
        ↓
在 <html> 应用 light/dark 标记
        ↓
浏览器首次绘制
        ↓
React Provider 以相同模式接管
```

首帧脚本只接受 `light | dark`；缺失或非法值回退 Light，以保持当前默认行为。脚本必须足够小且位于首次绘制前，不依赖 React effect。

### 切换阶段

```text
ThemeSwitcher
  → setMode(mode)
  → Provider 更新 mode
  → mode-storage 持久化
  → html 标记更新
  → AntD ThemeConfig 更新
  → useThemeTokens() 消费者获得新 Token
```

DOM 标记和 CSS Variable 写入只允许出现在主题模块内部。

### 未来管理员主题

未来仅替换首屏主题来源：

```text
当前已发布完整快照
        ↓
Next.js 服务端安全序列化到 <head>
        ↓
其余模式初始化流程保持不变
```

未登录页面不需要由浏览器额外请求主题。Next.js 服务端读取已发布快照并随 HTML 注入；主题快照不可用时使用内置默认主题。

## 本次迁移范围

1. 用新主题模块替代 `web/src/context/theme.tsx` 与 `web/src/constants/theme.ts`。
2. 将 locale 和 dayjs locale 责任移出 ThemeProvider。
3. 删除重复的共享 ThemeSwitcher，只保留控制台根壳唯一实现。
4. ThemeSwitcher 迁移到 `useThemeMode()`。
5. 所有 `themeName` 消费迁移到 `mode` 或 `useThemeTokens()`。
6. 图表颜色、拓扑和 Canvas 主题判断迁移到主题模块。
7. 清除主题模块外对 `localStorage.theme` 的直接读写。
8. 清除主题模块外对 `.dark` 的直接判断和写入。
9. 清除主题模块外对默认 Light/Dark ThemeConfig 的直接导入。
10. 将 `globals.css` 的主题颜色真值迁入 TypeScript，保留旧变量兼容别名。

本次不要求清理与主题行为无直接关系的所有历史硬编码颜色；发现的问题单独记录。

## 静态治理

增加定向架构检查，阻止主题模块以外出现：

```text
localStorage.getItem('theme')
localStorage.setItem('theme')
document.documentElement.classList.*('dark')
lightTheme / darkTheme 直接导入
```

检查应允许主题模块自身和明确的测试 fixture。新代码应通过主题模块公共出口导入，禁止深路径依赖内部 Adapter。

## 测试与验收

### 模块测试

- 默认 Light/Dark Token key 集合完全一致。
- 默认两套 Token 均无空值。
- 覆盖项正确合并，未覆盖项继承默认值。
- CSS Variables 与规范 Token 一一映射。
- 所有仍有消费者的旧 CSS Variable 均存在兼容别名。
- AntD 核心公开 Token 映射正确。
- `mode-storage` 兼容已有 `theme=light|dark`。
- 缺失或非法模式安全回退 Light。
- 主题序列化只允许白名单 Token 和合法颜色，不能产生 CSS 注入。

### 架构测试

- 业务代码没有直接操作主题存储或 DOM 模式。
- 业务代码没有导入主题模块内部实现。
- 图表等非 CSS 消费者通过 `useThemeTokens()` 获取颜色。

### 视觉验证

- 登录页和控制台首帧无 Light/Dark 闪烁。
- 主题切换行为与位置不变。
- 重构前后默认 Light/Dark 关键页面截图等价。
- Storybook 覆盖控制台根壳、菜单、Button、表单、Table、Tabs、Modal 和状态色。
- 检查 loading、empty、error、disabled、hover、active 和 focus。

### 仓库验证

- 定向主题测试通过。
- `pnpm type-check` 通过。
- `pnpm audit:component-ownership` 和 `pnpm check:component-ownership` 通过。
- Storybook 受已知构建基线阻塞时，保留原始错误证据，并至少完成定向 story 与类型验证。

## 未来主题管理模型

后续功能采用：

```text
管理员草稿
  → schemaVersion 迁移与 Token 白名单校验
  → Light/Dark 完整性和关键对比度校验
  → 生成不可变完整发布快照
  → 切换 ActiveThemePointer
  → 新页面加载或刷新时生效
```

主题管理约束：

- 草稿保存差异项，预览展示解析后的完整值。
- 预览在隔离 iframe/路由内运行，不污染管理后台本身。
- 关键正文、按钮、输入框和导航组合不满足最低对比度时阻止发布。
- 发布快照记录主题 ID、契约版本、主题版本、发布人和发布时间。
- 每次发布创建新快照，不原地覆盖历史。
- 回滚只切换当前指针。
- 升级读取旧主题时按 `schemaVersion` 在内存中迁移，不破坏历史快照。
- 新 Token 由旧主题继承新版默认值。
- 当前快照解析失败时回退上一份有效快照，再失败则回退内置默认主题。
- 主题失败不得导致登录页或 Control Console 白屏。

## 关键不变量

1. 业务页面不需要知道主题来源、继承、版本或 AntD 映射。
2. 默认主题是完整且构建时可用的最终兜底。
3. Light/Dark 必须定义相同的语义 Token 集合。
4. 一个语义 Token 的变化必须同时作用于 CSS、AntD 和显式 Token 消费者。
5. 首帧模式与 React hydration 后模式必须一致。
6. 未来发布失败或主题数据损坏不得阻断系统使用。
7. 本次重构不得造成视觉改版。
