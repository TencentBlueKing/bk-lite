# OpsPilot Web 与 WebChat 国际英文案一次性修正

Status: implemented

落地与计划的差异（以当前代码为准）：

- `GlobalWebchat` 用 `getStoredLocale()` 传 `locale`，不用 `useLocale()`。后者在 `LocaleProvider` 外会抛错，全局挂件测试不在该 Provider 里。
- 无 hook 的模块（`aguiMessageHandler`、`toolCallRenderer`、`downloadUrl`、`duration`、`memoryContent`）走 `web/src/app/opspilot/components/custom-chat-sse/i18n.ts` 的模块级词表；聊天挂载时 `setOpspilotModuleLocale`。`formatDurationMs` 默认仍按中文格式化，调用方传入 `t` 后跟随界面语言。
- 步骤无目标时的「步骤 {index}」在写入展示状态时翻译，不改后端字段。
- 技能设置里写入库的默认 Guide、画布「默认意图」、统一卡片的后端标签、Wiki 错误原文匹配、OKF 示例保持原文。
- 验收扫描是 `tmp/_scan_user_zh.py`：去掉注释、`t()`/`translate()` 兜底、正则和 `labelKey` 同行 label 后，用户向中文为 0。词条文件 `webchat-core/src/i18n.ts` 本身仍含中文。

## Problem Statement

`web/src/app/opspilot` 与 `webchat/` 两个范围存在成规模的中文硬编码，英文界面下直接漏出中文：

- `web/src/app/opspilot`：48 个文件、467 行面向用户的中文字面量（不含注释与测试夹具）。
- `webchat`：`webchat-ui` 14 个文件 100 行 + `webchat-core/src/platform.ts` 9 行，**且整个包没有任何 i18n 机制**——无 `useTranslation`、无 locale 词条，所有文案直接写死在组件与工具函数里。

两处根因不同，必须分别处理：

1. opspilot 侧已有 `t(id, defaultMessage?, values?)`（`web/src/utils/i18n.ts`，基于 react-intl，缺 key 回退 defaultMessage），缺的是把硬编码中文换成 `t()` 并补 `en.json` / `zh.json` 词条。
2. webchat 是独立 npm workspace，经 `webchat/scripts/sync-web-public.mjs` 构建成 UMD 塞进 `web/public/webchat/`，由 `web/src/app/(core)/components/global-webchat/index.tsx` 调 `window.WebChat.default(config, null)` 注入。它拿不到 web 的 React Context，**必须先建立自己的语言层**，再由 web 侧传当前语言。

约束：中文界面文案含义不得改变；英文仅在英文过长导致截断时缩短；不得做全仓格式化；范围严格限定上述两个目录。

## Solution

一次性扫干净，分三批落地：

**批 1（webchat）**：`webchat-core` 新增零依赖的 `i18n` 模块（`createTranslator` + 内置 zh/en 词条 + `locale` 传参），`webchat-ui` 全量组件改为经该层取词；web 侧 `GlobalWebchat` 用 `useLocale()` 传 `locale`，并把当前 `placeholder: '请输入消息...'` 硬编码一并改走 `t()`。

**批 2（opspilot 页面层）**：`(pages)/` 下的 tool 页、skill 的 settings/channel/chat、studio/chat、provider/detail 改为 `t()` + 补词条。

**批 3（opspilot 组件/常量/工具层）**：`custom-chat-sse` 展示组件、severity badge、tool 抽屉、chatflow 格式化、`utils/duration`、`utils/memoryContent` 等。

最终用扫描脚本证明两范围内不再有面向用户的硬编码中文。

## 硬约束：不许改的部分

以下中文虽被扫描命中，但属于**协议契约或后端数据匹配**，翻译会破坏功能：

| 位置 | 内容 | 原因 |
|---|---|---|
| `custom-chat-sse/toolResultStatus.ts:7` | `/无法加载\s*kubernetes\|请检查 kubeconfig\|.../i` | 正则匹配后端返回的中文错误串 |
| `custom-chat-sse/ToolCallGroup.tsx:55`、`toolCallRenderer.tsx:342,413` | `/(?:用户回答\|选择了\|默认选项)[:：]\s*(.+?)/` | 正则解析 `request_user_choice` 工具回填的中文结果串 |
| `custom-chat-sse/downloadUrl.ts:140,143,208,267,272,307` | `/地址\s*[:：]/`、`/\{token\}\|加密token/i`、`/下载/` | 匹配模型输出的下载链接文本 |
| `custom-chat-sse/ConfigAnalysisReportCard.tsx:92,255,316,355` | `'信息不完整'` 等作为 key 传给 `title=` 的是已转 `t()` 的**服务端枚举值** | 需逐条判定：仅当为本地渲染常量才改 |
| `unified-ops-card/index.tsx:65,66,93-96` | `/记忆条数/`、`团队/个人/上线/下线` 作语义色板 key | 匹配**后端返回**的卡片标签文本 |
| `opspilot-selector-shared/contracts.ts:45,46` | `n.includes('知识库')` | 匹配后端返回的知识库/工具名 |
| `constants/chatflow.ts:173`、`chatflow/nodes/index.tsx:86,90,96` | `默认意图`、`意图${index+1}` | **保存进画布数据**的节点默认名，改了会变更既有数据语义 |
| `utils/wikiMarkdownImport.ts:11` | `OKF_FRONTMATTER_EXAMPLE` 的 `title: 页面标题` | 协议示例常量，同上 |
| `custom-chat-sse/plannedExecutionState.ts:123,150` | `步骤 ${stepIndex}` | 由前端生成的步骤 objective 展示串，需确认是否落库后再定 |
| `toolCallRenderer.tsx:110-261` | `verbMap` / `nounMap` 词表 | 词表**本身是中文**，但用途是把英文工具名转成可读串；这属于应 i18n 的展示逻辑（见下） |

## User Stories

1. As a 英文界面用户, I want opspilot 页面不再出现中文字面量, so that 界面语言一致。
2. As a 英文界面用户, I want 悬浮机器人（webchat）文案跟随站点语言切换, so that 机器人不与主界面语言冲突。
3. As a 中文界面用户, I want 现有中文文案含义逐字不变, so that 切换本次变更不引入体验回退。
4. As a 后端维护者, I want 匹配后端中文错误串/枚举值的正则与常量保持原样, so that 翻译不会打断数据契约。

## Implementation Decisions

### 语言层放在 webchat-core

`webchat-core` 是 `webchat-ui` 的唯一内部依赖（`"@webchat/core": "1.0.0"`），把语言层放这里可让两个包共用，且 core 本身有 `formatSessionTime` 等需要翻译的纯函数。

- 新增 `webchat/packages/webchat-core/src/i18n.ts`：
  - `export type Locale = 'zh' | 'en'`
  - `createTranslator(locale, catalogOverride?)` 返回 `t(key, fallback?)`，缺 key 回退 `fallback ?? key`（对齐 web 侧 `formatFallback` 语义）。
  - 内置 `zh` / `en` 两份平铺词条（`Record<string, string>`）。
  - `setWebChatLocale(locale)` / `getWebChatLocale()` 供 webchat-ui 的模块级函数（如 `imageBudget.ts` 的 throw 文案）取词——这些函数在 React 树外，没有 props 可穿。
- 词条 key 用点号命名空间，与 web 侧风格一致：`chat.inputPlaceholder`、`session.new`、`session.justNow`…
- **ICU 不用**（webchat 不引第三方依赖），需要变量时用 `t('key', 'fallback').replace('{n}', String(n))`，由 `t()` 内部统一处理 `{name}` 占位替换，与 `web/src/utils/i18n.ts` 的 `formatFallback` 同形。

### locale 传递链路

`ChatProps` 已作为 `FloatingButtonProps` / `PlatformChatProps` 的基类被导出，新增字段会自动贯通到 `window.WebChat.default(config)`：

```
web LocaleProvider(useLocale)
  → GlobalWebchat: locale={locale}
  → window.WebChat.default({ ..., locale, placeholder: t('webchat.inputPlaceholder') })
  → FloatingButton → PlatformChat → Chat
  → createTranslator(locale) → t('...')
```

- `placeholder` 当前是硬编码 `'请输入消息...'`（`global-webchat/index.tsx:157`），改由 web 侧 `t('webchat.inputPlaceholder')` 提供；webchat 内部仍保留默认值以支持独立使用。
- `Chat.tsx` 内新增 `useTranslator()`（内部包一层 React context 或直接按 `locale` prop `useMemo`），避免逐层透传。
- `webchat-core` 的纯函数（`formatSessionTime`、`mapPlatformSessions`、`mapPlatformApplications`）增加可选 `t` 参数，默认取当前全局 locale。**`tests/core/platform.test.ts` 现有断言写死中文**（如 `assert.equal(formatSessionTime(...), '刚刚')`），默认 locale 为 `zh` 时行为不变，测试无需改；另补一条 en 断言证明切换生效。

### opspilot 侧的 labelKey 模式

`constants/provider.ts`、`modelManagement.tsx` 等常量表是「值 → 中文 label」结构，改为 `{ label, labelKey }`，渲染处 `t(labelKey, label)`。这样中文兜底仍留在代码里，缺词条时行为与今天一致。

`unified-ops-card` 的语义色板 key（`团队/个人/上线/下线`）**保持原样不动**——它匹配的是后端返回的 label，不是前端生成的文案。

### custom-chat-sse 的 HTML 字符串渲染器

`toolCallRenderer.tsx` 用模板字符串拼 HTML（非 React 渲染），无 hook 可用。做法：

- `renderAllToolCalls` / `renderToolItem` / `renderErrorMessage` 增加可选 `t` 参数。
- `generateDefaultSummary` 的 `verbMap` / `nounMap` 改为 `Record<string, {zh, en}>` 或 `Record<string, string>` + `t('toolCall.verb.check')`；词条量大（~150 条），拆成 `toolCallVerb.*` / `toolCallNoun.*` 两个命名空间。
- 唯一持有 `t` 的入口是 `custom-chat-sse/index.tsx` 与 `aguiMessageHandler.ts`（已是 class/组件内，可从上层传）。

## 批次与文件清单

### 批 1：webchat

| 文件 | 动作 |
|---|---|
| `webchat/packages/webchat-core/src/i18n.ts` | 新增：locale 类型、词条、`createTranslator`、全局 locale 存取 |
| `webchat/packages/webchat-core/src/index.ts` | 导出语言层 |
| `webchat/packages/webchat-core/src/platform.ts` | 9 行：新增会话/相对时间/渠道占位走 `t` |
| `webchat/packages/webchat-ui/src/chatProps.ts` | 新增 `locale?: Locale` |
| `webchat/packages/webchat-ui/src/Chat.tsx` | 19 行 + 建立 `useTranslator` |
| `webchat/packages/webchat-ui/src/PlatformChat.tsx` | 27 行 |
| `webchat/packages/webchat-ui/src/FloatingButton.tsx` | 2 行 |
| `webchat/packages/webchat-ui/src/aguiEventHandler.ts` | 2 行 |
| `webchat/packages/webchat-ui/src/imageBudget.ts` | 4 行（模块级，走全局 locale） |
| `webchat/packages/webchat-ui/src/components/{ConfirmDialog,ContextUsageRing,ConversationSkeleton,HitlPanels,MessageActions,MessageBubble,PillComposer,ThinkingPanel,ToolCallDisplay}.tsx` | 45 行 |
| `web/src/app/(core)/components/global-webchat/index.tsx` | 传 `locale` + `placeholder` 走 `t()` |
| `webchat/tests/core/platform.test.ts` | 补 en 断言 |
| `webchat/tests/webchat-i18n.test.mjs`（新） | 断言词条两侧齐全、组件源码无裸中文 |

验证：`cd webchat && npm test`、`cd web && pnpm test:global-webchat`。

### 批 2：opspilot 页面层

`(pages)/provider/detail/page.tsx` (4)、`(pages)/skill/chat/page.tsx` (20)、`(pages)/skill/detail/channel/page.tsx` (4)、`(pages)/skill/detail/settings/page.tsx` (21)、`(pages)/studio/chat/page.tsx` (8)、`(pages)/tool/page.tsx` (20)；`components/skill/toolSelector.tsx` (4)、`components/tool/SkillPackageDetailDrawer.tsx` (17)、`components/opspilot-tool-editor/skill-import-modal.tsx` (6)、`components/provider/{modelManagement.tsx,vendor-grid.tsx}` (5)。

注意：`(pages)/skill/chat/page.tsx` 与 `(pages)/studio/chat/page.tsx` 的「新会话」标题是**会话创建时落库的字符串**（`title: 新会话 ${toLocaleString}`），本轮只改展示层兜底文案，不改写入库的标题格式——除非确认这些会话标题不参与匹配逻辑。**该点需在实现时读代码确认，不能假设。**

验证：`cd web && pnpm lint`、`pnpm type-check`、相关 vitest。

### 批 3：opspilot 组件/常量层

`custom-chat-sse/`：`ConfigAnalysisReportCard.tsx` (37)、`DiffReportCard.tsx` (10)、`PlannedExecutionSteps.tsx` (16)、`downloadUrl.ts` (8，仅展示串)、`diffReportItemPresentation.ts` (8)、`ToolCallGroup.tsx` (7)、`index.tsx` (6)、`aguiMessageHandler.ts` (6)、`RepairCommandsCard.tsx` (5)、`UserChoiceCard.tsx` (6)、`SkillView.tsx` (3)、`liveYamlRequest.ts` (2)、`plannedExecutionState.ts` (2)、`configAnalysisReportSummary.ts` (3)、`PlannedExecutionStatus.tsx` (2)、`historyMessageProcessor.ts` (2)、`toolCallRenderer.tsx` (154)、`ContextUsageRing.tsx` (1)、`toolResultStatus.ts` (0，仅确认不动)。

其余：`opspilot-config-severity-badge/index.tsx` (7)、`opspilot-entity-detail-intro/index.tsx` (2)、`opspilot-selector-operate-modal/index.tsx` (1)、`chatflow/utils/formatConfigInfo.ts` (6)、`chatflow/components/nodeConfigs/{EnterpriseWechat,WechatOfficial}NodeConfig.tsx` (各 3)、`tool/urlInputWithButton.tsx` (1)、`wiki/BuildRecordTab.tsx` (11，仅 t() 的 defaultMessage 归位)、`wiki/MaterialTab.tsx` (3)、`utils/duration.ts` (4)、`utils/memoryContent.ts` (2)、`constants/provider.ts` (11)、`constants/chatflow.ts` (2，仅展示用 label)。

验证：同批 2，另加新增 `web/scripts/opspilot-i18n-coverage-test.ts` 扫描断言。

## 测试与验收

1. **webchat**：`npm test` 全绿；新增 `webchat-i18n.test.mjs` 证明 zh/en 词条键集合一致、且组件源码中不再有裸中文展示串。
2. **web**：`pnpm lint`；改动涉及类型/布局时 `pnpm type-check`；`pnpm test:global-webchat`；opspilot 相关 vitest（skill detail channel/settings 已有测试需保持绿）。
3. **静态扫描**：`tmp/_scan_zh.py` 复跑，opspilot + webchat 命中行数应从 467/109 降到「仅剩批 1 表格中列出的协议常量与正则」。
4. **中文不变**：zh.json 新增词条的中文值必须与原硬编码逐字一致（脚本可校验）。

## Out of Scope

- server 端 `LanguageLoader` / `operation_analysis` 等 YAML 文案。
- 非 opspilot 的 web app（monitor/alarm/cmdb 等）残留硬编码。
- webchat 的 `webchat-demo` 包。
- 全仓格式化与无关重构。
