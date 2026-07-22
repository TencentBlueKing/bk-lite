# Historical Superpowers change: 2026-07-14-node-manager-command-copy-dialog

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-14-node-manager-command-copy-dialog.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为节点管理的控制器安装命令和云区域代理部署脚本提供真实等待剪贴板结果、展示完整复制原文且可重试的统一结果弹窗。

**Architecture:** 新增无 React 依赖的异步剪贴板工具和可测试的复制状态 reducer，再由 `useCommandCopyDialog` 组合 Ant Design Modal。三个页面入口只负责准备原文和调用共享 Hook；普通调试字段与配置复制保持现状。

**Tech Stack:** Next.js 16、React 19、TypeScript 5、Ant Design 5、项目 `tsx` 专项测试脚本、pnpm。

## Global Constraints

- 仅覆盖控制器操作指引、控制器安装进度页、云区域代理部署脚本三个命令/脚本入口。
- Artifact JSON、安装器调试字段和采集器配置继续使用轻提示。
- 只有浏览器确认写入成功后才能显示“已复制到剪切板”。
- 成功和失败弹窗都展示完整只读原文；失败提供重试或手动选择恢复路径。
- 复制原文不写日志、埋点、本地存储或错误上报，关闭弹窗后从 Hook 状态清除。
- 不修改后端接口，不增加新依赖，不引入全局 Provider。
- 中文、英文文案同步维护。
- 所有功能改动遵循 TDD：先看到专项测试失败，再写最小实现。

---

## 文件结构

- `web/src/app/node-manager/utils/clipboard.ts`：浏览器剪贴板写入与兼容分支，纯 TypeScript、可注入环境。
- `web/src/app/node-manager/hooks/useCommandCopyDialog.tsx`：复制状态 reducer、异步复制编排和 Ant Design 结果弹窗。
- `web/scripts/node-manager-command-copy-dialog-test.ts`：剪贴板行为、状态转换、i18n 和三个入口接线的专项回归。
- `web/package.json`：新增专项测试命令。
- `web/src/app/node-manager/locales/{zh,en}.json`：结果弹窗文案。
- `web/src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidance.tsx`：接入共享 Hook。
- `web/src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidanceSections.tsx`：复制按钮禁用与加载态。
- `web/src/app/node-manager/(pages)/cloudregion/node/operationProgress/index.tsx`：命令接口返回后调用共享 Hook。
- `web/src/app/node-manager/(pages)/cloudregion/environment/page.tsx`：代理部署脚本调用共享 Hook，移除复制即成功的旧确认框。

---

### Task 1: 异步剪贴板工具

**Files:**
- Create: `web/src/app/node-manager/utils/clipboard.ts`
- Create: `web/scripts/node-manager-command-copy-dialog-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Produces: `copyText(value: string, environment?: ClipboardEnvironment): Promise<void>`。
- Produces: `ClipboardCopyError`，`reason` 为 `empty`、`unavailable` 或 `failed`。
- Consumes: 浏览器 `navigator.clipboard` 或 `document.execCommand('copy')`。

- [ ] **Step 1: 写剪贴板工具失败测试**

创建专项脚本，先覆盖现代 API 成功/拒绝、兼容分支 true/false、空内容和临时元素清理。测试使用可注入环境，不依赖真实浏览器：

```ts
import assert from 'node:assert/strict';
import {
  ClipboardCopyError,
  copyText,
  type ClipboardEnvironment
} from '../src/app/node-manager/utils/clipboard.ts';

let written = '';
await copyText('echo hello', {
  writeText: async (value) => { written = value; }
});
assert.equal(written, 'echo hello');

await assert.rejects(
  copyText('echo denied', {
    writeText: async () => { throw new Error('denied'); }
  }),
  (error: unknown) => error instanceof ClipboardCopyError && error.reason === 'failed'
);

let fallbackValue = '';
await copyText('echo fallback', {
  fallbackCopy: (value) => { fallbackValue = value; return true; }
});
assert.equal(fallbackValue, 'echo fallback');

await assert.rejects(
  copyText('echo false', { fallbackCopy: () => false }),
  (error: unknown) => error instanceof ClipboardCopyError && error.reason === 'failed'
);

await assert.rejects(
  copyText('   ', { fallbackCopy: () => true }),
  (error: unknown) => error instanceof ClipboardCopyError && error.reason === 'empty'
);
```

在 `package.json` 增加：

```json
"test:node-manager-command-copy-dialog": "pnpm exec tsx scripts/node-manager-command-copy-dialog-test.ts"
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `cd web && pnpm test:node-manager-command-copy-dialog`

Expected: FAIL，提示找不到 `src/app/node-manager/utils/clipboard.ts`。

- [ ] **Step 3: 实现最小剪贴板工具**

实现明确环境接口、错误类型和浏览器默认适配器：

```ts
export type ClipboardCopyFailureReason = 'empty' | 'unavailable' | 'failed';

export class ClipboardCopyError extends Error {
  constructor(public readonly reason: ClipboardCopyFailureReason, cause?: unknown) {
    super(reason);
    this.name = 'ClipboardCopyError';
    if (cause !== undefined) this.cause = cause;
  }
}

export interface ClipboardEnvironment {
  writeText?: (value: string) => Promise<void>;
  fallbackCopy?: (value: string) => boolean;
}

const fallbackCopy = (value: string): boolean => {
  if (typeof document === 'undefined') return false;
  const textArea = document.createElement('textarea');
  textArea.value = value;
  textArea.setAttribute('readonly', '');
  textArea.style.position = 'fixed';
  textArea.style.opacity = '0';
  document.body.appendChild(textArea);
  try {
    textArea.select();
    return document.execCommand('copy');
  } finally {
    document.body.removeChild(textArea);
  }
};

const browserEnvironment = (): ClipboardEnvironment => ({
  writeText:
    typeof navigator !== 'undefined' && navigator.clipboard?.writeText
      ? (value) => navigator.clipboard.writeText(value)
      : undefined,
  fallbackCopy
});

export const copyText = async (
  value: string,
  environment: ClipboardEnvironment = browserEnvironment()
): Promise<void> => {
  if (!value.trim()) throw new ClipboardCopyError('empty');
  try {
    if (environment.writeText) {
      await environment.writeText(value);
      return;
    }
    if (!environment.fallbackCopy) throw new ClipboardCopyError('unavailable');
    if (!environment.fallbackCopy(value)) throw new ClipboardCopyError('failed');
  } catch (error) {
    if (error instanceof ClipboardCopyError) throw error;
    throw new ClipboardCopyError('failed', error);
  }
};
```

- [ ] **Step 4: 运行专项测试并确认绿灯**

Run: `cd web && pnpm test:node-manager-command-copy-dialog`

Expected: PASS，退出码 0。

- [ ] **Step 5: 提交剪贴板工具**

```bash
git add web/package.json web/scripts/node-manager-command-copy-dialog-test.ts web/src/app/node-manager/utils/clipboard.ts
git commit -m "测试: 覆盖节点管理命令复制结果"
```

---

### Task 2: 共享复制状态与结果弹窗

**Files:**
- Create: `web/src/app/node-manager/hooks/useCommandCopyDialog.tsx`
- Modify: `web/scripts/node-manager-command-copy-dialog-test.ts`
- Modify: `web/src/app/node-manager/locales/zh.json`
- Modify: `web/src/app/node-manager/locales/en.json`

**Interfaces:**
- Consumes: `copyText(value): Promise<void>` 和 `ClipboardCopyError.reason`。
- Produces: `useCommandCopyDialog(): { copyCommand; commandCopyDialog; copying }`。
- `copyCommand(value: string, options?: { descriptionKey?: string }): Promise<boolean>`。

- [ ] **Step 1: 写 reducer 与文案失败测试**

在专项脚本追加状态行为测试和 locale 键检查：

```ts
import {
  commandCopyInitialState,
  commandCopyReducer
} from '../src/app/node-manager/hooks/useCommandCopyDialog.tsx';
import { readFileSync } from 'node:fs';

const copying = commandCopyReducer(commandCopyInitialState, {
  type: 'copying',
  content: 'echo hello'
});
assert.equal(copying.copying, true);
assert.equal(copying.content, 'echo hello');

const success = commandCopyReducer(copying, { type: 'success' });
assert.equal(success.open, true);
assert.equal(success.status, 'success');
assert.equal(success.copying, false);

const failure = commandCopyReducer(copying, { type: 'failure', reason: 'failed' });
assert.equal(failure.open, true);
assert.equal(failure.status, 'error');
assert.equal(failure.content, 'echo hello');

const closed = commandCopyReducer(failure, { type: 'close' });
assert.deepEqual(closed, commandCopyInitialState);

const locales = ['zh', 'en'].map((name) => JSON.parse(
  readFileSync(new URL(`../src/app/node-manager/locales/${name}.json`, import.meta.url), 'utf8')
));
for (const locale of locales) {
  const node = locale['node-manager'].cloudregion.node;
  for (const key of [
    'commandCopySuccessTitle', 'commandCopySuccessDesc',
    'commandCopyFailedTitle', 'commandCopyFailedDesc',
    'commandCopyEmptyDesc', 'copiedOriginal', 'copyAgain',
    'retryCopy', 'gotIt'
  ]) assert.equal(typeof node[key], 'string');
}
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `cd web && pnpm test:node-manager-command-copy-dialog`

Expected: FAIL，提示找不到 `useCommandCopyDialog.tsx` 或新增 locale 键不存在。

- [ ] **Step 3: 实现 reducer、Hook 和 Modal**

状态必须包含：

```ts
export interface CommandCopyState {
  open: boolean;
  copying: boolean;
  content: string;
  status: 'success' | 'error' | null;
  reason: ClipboardCopyFailureReason | null;
  descriptionKey?: string;
}
```

Reducer 支持 `copying`、`success`、`failure`、`close`；`close` 必须回到不含原文的初始状态。Hook 的 `copyCommand` 必须 `await copyText(value)`，返回布尔结果，并在 `finally` 前通过 reducer 消除加载态。

Modal 使用以下固定结构：

```tsx
<Modal
  open={state.open}
  width={680}
  title={state.status === 'success' ? successTitle : failedTitle}
  onCancel={close}
  focusTriggerAfterClose
  footer={[
    state.reason !== 'empty' && (
      <Button key="copy" loading={state.copying} onClick={retryCopy}>
        {state.status === 'success' ? copyAgain : retryCopyLabel}
      </Button>
    ),
    <Button key="close" type="primary" onClick={close}>{gotIt}</Button>
  ]}
>
  <Alert type={state.status === 'success' ? 'success' : 'error'} showIcon />
  <div className="mt-[16px] text-[12px] text-[var(--color-text-3)]">{copiedOriginal}</div>
  <pre className="mt-[8px] max-h-[240px] overflow-auto whitespace-pre rounded-[6px] bg-[var(--color-fill-1)] p-[12px] font-mono text-[12px] text-[var(--color-text-1)]">
    {state.content}
  </pre>
</Modal>
```

空内容错误不执行 `copyText`，直接进入 `reason: 'empty'`；空内容状态不渲染“重试复制”按钮。失败信息不拼接浏览器异常和原文。

- [ ] **Step 4: 添加中英文文案**

中文：

```json
"commandCopySuccessTitle": "已复制到剪切板",
"commandCopySuccessDesc": "请核对命令后，在目标主机中执行。",
"commandCopyFailedTitle": "复制失败",
"commandCopyFailedDesc": "浏览器未能写入剪切板，请重试或手动选择下方原文。",
"commandCopyEmptyDesc": "未获取到可复制内容，请重新获取命令后再试。",
"copiedOriginal": "复制原文",
"copyAgain": "再次复制",
"retryCopy": "重试复制",
"gotIt": "知道了"
```

英文使用语义对应的 `Copied to clipboard`、`Copy failed`、`Copied content`、`Copy again`、`Retry copy` 和 `Got it`。

- [ ] **Step 5: 运行专项测试与触及文件 ESLint**

Run: `cd web && pnpm test:node-manager-command-copy-dialog`

Expected: PASS。

Run: `cd web && pnpm exec eslint src/app/node-manager/utils/clipboard.ts src/app/node-manager/hooks/useCommandCopyDialog.tsx scripts/node-manager-command-copy-dialog-test.ts`

Expected: 0 errors。

- [ ] **Step 6: 提交共享弹窗能力**

```bash
git add web/src/app/node-manager/hooks/useCommandCopyDialog.tsx web/src/app/node-manager/locales/zh.json web/src/app/node-manager/locales/en.json web/scripts/node-manager-command-copy-dialog-test.ts
git commit -m "功能: 新增节点管理命令复制结果弹窗"
```

---

### Task 3: 接入控制器命令复制入口

**Files:**
- Modify: `web/src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidance.tsx`
- Modify: `web/src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidanceSections.tsx`
- Modify: `web/src/app/node-manager/(pages)/cloudregion/node/operationProgress/index.tsx`
- Modify: `web/scripts/node-manager-command-copy-dialog-test.ts`

**Interfaces:**
- Consumes: `copyCommand(value): Promise<boolean>`、`commandCopyDialog`、`copying`。
- Preserves: `useHandleCopy` 仅供调试字段和 Artifact JSON 使用。

- [ ] **Step 1: 写控制器入口失败测试**

在专项脚本读取三个源文件并断言行为接线：

```ts
const guidance = readFileSync('../web/src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidance.tsx', 'utf8');
assert.match(guidance, /useCommandCopyDialog/);
assert.match(guidance, /copyCommand\(nodeInfo\.installerSession/);
assert.match(guidance, /commandCopyDialog/);
assert.match(guidance, /handleCopy\(\{ value \}\)/); // 调试值保持轻提示

const sections = readFileSync('../web/src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidanceSections.tsx', 'utf8');
assert.match(sections, /disabled=\{loading \|\| !installerSession\.trim\(\)\}/);
assert.match(sections, /loading=\{copying\}/);

const progress = readFileSync('../web/src/app/node-manager/(pages)/cloudregion/node/operationProgress/index.tsx', 'utf8');
assert.match(progress, /await copyCommand\(installCommand/);
assert.doesNotMatch(progress, /notification\.success\(\{[\s\S]*commandCopied/);
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `cd web && pnpm test:node-manager-command-copy-dialog`

Expected: FAIL，三个入口尚未接入共享 Hook。

- [ ] **Step 3: 接入操作指引**

- 保留 `useHandleCopy` 给 `handleCopyDebugValue`。
- 新增 `useCommandCopyDialog`，主命令 `handleCopyCommand` 改为 `void copyCommand(nodeInfo.installerSession)`。
- 在 Drawer 内容末尾渲染 `{commandCopyDialog}`。
- `SessionEditor` 新增 `copying` 属性，复制按钮使用 `loading={copying}` 和 `disabled={loading || !installerSession.trim()}`。
- Windows 和 Linux section 同步传递 `copying`。

- [ ] **Step 4: 接入安装进度页**

- 新增 `useCommandCopyDialog`。
- 保留 `copyingNodeIds` 覆盖“请求命令 + 写剪贴板”的整段加载。
- `getInstallCommand` 返回后调用 `await copyCommand(installCommand)`。
- 删除原 `notification.success` 及其平台分支描述；请求失败继续交由请求层处理。
- 在组件 JSX 根部附近渲染 `{commandCopyDialog}`。

- [ ] **Step 5: 运行专项测试和控制器相关回归**

Run: `cd web && pnpm test:node-manager-command-copy-dialog && pnpm test:installer-progress`

Expected: 两个脚本均 PASS。

Run: `cd web && pnpm exec eslint 'src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidance.tsx' 'src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidanceSections.tsx' 'src/app/node-manager/(pages)/cloudregion/node/operationProgress/index.tsx'`

Expected: 0 errors。

- [ ] **Step 6: 提交控制器入口接入**

```bash
git add web/src/app/node-manager/'(pages)'/cloudregion/node/controllerInstall/installing/operationGuidance.tsx web/src/app/node-manager/'(pages)'/cloudregion/node/controllerInstall/installing/operationGuidanceSections.tsx web/src/app/node-manager/'(pages)'/cloudregion/node/operationProgress/index.tsx web/scripts/node-manager-command-copy-dialog-test.ts
git commit -m "功能: 统一控制器命令复制反馈"
```

---

### Task 4: 接入云区域代理部署脚本并收口

**Files:**
- Modify: `web/src/app/node-manager/(pages)/cloudregion/environment/page.tsx`
- Modify: `web/scripts/node-manager-command-copy-dialog-test.ts`

**Interfaces:**
- Consumes: `copyCommand(script)`、`commandCopyDialog`、`copying`。
- Removes: 复制后无条件 `Modal.confirm` 和与其绑定的刷新代理状态动作。

- [ ] **Step 1: 写代理脚本入口失败测试**

在专项脚本追加：

```ts
const environmentPage = readFileSync('../web/src/app/node-manager/(pages)/cloudregion/environment/page.tsx', 'utf8');
assert.match(environmentPage, /useCommandCopyDialog/);
assert.match(environmentPage, /copyCommand\(script/);
assert.match(environmentPage, /commandCopyDialog/);
assert.doesNotMatch(environmentPage, /title:\s*t\('node-manager\.cloudregion\.environment\.copySuccess'\)/);
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `cd web && pnpm test:node-manager-command-copy-dialog`

Expected: FAIL，环境页面仍使用旧 `useHandleCopy` 和无条件成功确认框。

- [ ] **Step 3: 接入代理部署脚本**

- 移除环境页面的 `useHandleCopy`。
- 调用 `useCommandCopyDialog`。
- `copyScript` 改为 `void copyCommand(script)`。
- “复制脚本”按钮使用 `loading={copying}`，并继续只在 `script` 非空时渲染。
- 在页面 JSX 根部附近渲染 `{commandCopyDialog}`。
- 删除仅服务旧复制成功弹窗的 `CheckCircleFilled` import；保留页面其他用途的 `Modal`、`SyncOutlined` 和刷新函数。

- [ ] **Step 4: 运行专项测试、全部触及文件 ESLint 和 TypeScript 门禁**

Run: `cd web && pnpm test:node-manager-command-copy-dialog && pnpm test:installer-progress`

Expected: PASS。

Run: `cd web && pnpm exec eslint src/app/node-manager/utils/clipboard.ts src/app/node-manager/hooks/useCommandCopyDialog.tsx 'src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidance.tsx' 'src/app/node-manager/(pages)/cloudregion/node/controllerInstall/installing/operationGuidanceSections.tsx' 'src/app/node-manager/(pages)/cloudregion/node/operationProgress/index.tsx' 'src/app/node-manager/(pages)/cloudregion/environment/page.tsx' scripts/node-manager-command-copy-dialog-test.ts`

Expected: 0 errors。

Run: `cd web && NEXTAPI_INSTALL_APP=node-manager pnpm precommit && pnpm exec tsc -p tsconfig.lint.json --noEmit`

Expected: 退出码 0；若任务外既有错误阻断，保存完整错误并确认触及文件未新增错误。

- [ ] **Step 5: 检查安全与范围**

Run: `rg -n "console\.|localStorage|sessionStorage|notification\.success" web/src/app/node-manager/utils/clipboard.ts web/src/app/node-manager/hooks/useCommandCopyDialog.tsx web/src/app/node-manager/'(pages)'/cloudregion/node/controllerInstall/installing/operationGuidance.tsx web/src/app/node-manager/'(pages)'/cloudregion/node/operationProgress/index.tsx web/src/app/node-manager/'(pages)'/cloudregion/environment/page.tsx`

Expected: 新增复制能力不记录原文；安装进度页不再存在旧的命令复制成功 notification。

- [ ] **Step 6: 提交代理脚本接入**

```bash
git add web/src/app/node-manager/'(pages)'/cloudregion/environment/page.tsx web/scripts/node-manager-command-copy-dialog-test.ts
git commit -m "功能: 统一代理部署脚本复制反馈"
```

---

### Task 5: 最终验证与项目记忆收口

**Files:**
- No application file changes expected.

**Interfaces:**
- Consumes: 前四个任务的提交与测试命令。
- Produces: 可复核的测试、静态检查和项目记忆证据。

- [ ] **Step 1: 运行最终专项验证**

Run: `cd web && pnpm test:node-manager-command-copy-dialog && pnpm test:installer-progress`

Expected: 全部 PASS。

- [ ] **Step 2: 运行最终触及文件 ESLint**

Run: Task 4 Step 4 的 ESLint 命令。

Expected: 0 errors。

- [ ] **Step 3: 运行节点管理 TypeScript 门禁**

Run: `cd web && NEXTAPI_INSTALL_APP=node-manager pnpm precommit && pnpm exec tsc -p tsconfig.lint.json --noEmit`

Expected: 退出码 0，或记录可证明与本任务无关的既有阻断。

- [ ] **Step 4: 审查最终 diff**

Run: `git diff --check HEAD~3..HEAD && git status --short`

Expected: 无空白错误；仅存在本计划文件和目标 Web 文件的提交，用户既有未提交内容未被纳入。

- [ ] **Step 5: 更新 projectmem**

- 对 #0038、#0040、#0041 逐项记录成功尝试和经测试确认的修复。
- #0039 的采集器配置兼容分支不在本次范围内，保持 open。
- 记录专项测试与 TypeScript/ESLint 结果。

## specs: 2026-07-14-node-manager-command-copy-dialog-design.md

## 背景

节点管理当前有多处命令或脚本复制入口：

- 控制器操作指引中的安装命令；
- 控制器安装进度页中的安装命令；
- 云区域环境中的代理部署脚本。

这些入口复用的 `useHandleCopy` 没有等待 `navigator.clipboard.writeText()` 返回的 Promise。浏览器拒绝写入剪贴板时，页面仍可能立即显示“复制成功”并引导用户执行命令。用户随后粘贴的可能是剪贴板中的旧内容，属于运维执行安全风险。

本优化统一命令和脚本的复制反馈：只有浏览器确认写入成功后才显示成功状态，并在结果弹窗内展示本次复制的完整原文，方便用户核对。

## 目标

- 点击命令或脚本复制入口后，等待真实剪贴板写入结果。
- 成功时弹出结果窗口，明确显示“已复制到剪切板”。
- 在弹窗内展示本次实际复制的完整原文。
- 失败时不得显示成功状态，并提供重试和手动复制的恢复路径。
- 三个目标入口共用相同能力、状态语义和中英文文案。
- 复制内容仅保存在当前页面内存中，不写日志、不持久化。

## 非目标

- 不修改后端命令生成接口。
- 不增加复制操作审计日志。
- 不改变 Artifact JSON、安装器调试字段、采集器配置等普通内容复制交互。
- 不建设全站级复制弹窗 Provider。
- 不改变命令内容、转义、参数或执行方式。

## 适用范围

### 纳入统一结果弹窗

1. 控制器操作指引中的安装命令复制。
2. 控制器安装进度页中的安装命令复制。
3. 云区域环境中的代理部署脚本复制。

### 继续使用轻提示

- 安装器平台、版本、下载地址和对象存储 Key 等调试字段；
- Artifact JSON；
- 采集器配置编辑器内容；
- 节点管理之外的普通文本复制。

## 方案比较

### 方案 A：共享复制 Hook 与统一结果弹窗（采用）

新增节点管理专用的 `useCommandCopyDialog`，封装剪贴板写入、状态管理、结果弹窗和再次复制。各入口只提供复制原文、内容类型和可选提示。

优点：

- 三个入口状态语义一致；
- 复制成功、失败和空内容规则只实现一次；
- 便于测试和后续新增命令复制入口；
- 改动局限在节点管理模块。

代价：需要抽取一个可独立测试的剪贴板工具和一个共享 Hook/弹窗组件。

### 方案 B：各页面独立维护弹窗

优点是单页改动直观，缺点是三个入口重复实现状态、错误处理和文案，后续容易再次分叉，因此不采用。

### 方案 C：全站复制弹窗 Provider

优点是扩展范围最大，缺点是本次仅要求节点管理命令/脚本复制，全站改造超出需求且增加上下文依赖，因此不采用。

## 组件与职责

### 剪贴板工具

提供一个不依赖 React 的异步复制函数：

- 输入必须是非空字符串；空字符串和仅空白字符串视为不可复制；
- 优先 `await navigator.clipboard.writeText(value)`；
- Clipboard API 不可用时使用隐藏 `textarea` 兼容复制；
- 兼容分支必须检查 `document.execCommand('copy')` 返回值；返回 `false` 视为失败；
- 无论成功或失败都清理临时 DOM；
- 失败通过明确的错误结果或异常返回给调用方，不在工具内部展示 UI。

### `useCommandCopyDialog`

负责：

- 接收复制原文和内容类型；
- 管理首次复制与再次复制的加载状态；
- 调用剪贴板工具并等待真实结果；
- 管理结果弹窗的成功或失败状态；
- 在失败后保留原文并允许重试；
- 向调用方提供触发函数和弹窗节点。

普通文本复制继续使用现有轻提示能力，不通过此 Hook。

### 结果弹窗

使用现有 Ant Design `Modal`、成功/错误图标、Button 和项目主题变量，不引入新的视觉体系。

弹窗内容：

- 状态标题：成功为“已复制到剪切板”，失败为“复制失败”；
- 状态说明：成功时提醒用户核对后在目标主机执行，失败时提示重试或手动选择原文；
- “复制原文”只读代码区域；
- 次按钮：成功状态为“再次复制”，失败状态为“重试复制”；
- 主按钮：“知道了”。

## 交互与状态

### 首次复制

```text
用户点击复制
  -> 获取或读取命令原文
  -> 校验原文非空
  -> 复制按钮进入加载态
  -> 等待 Clipboard API 或兼容分支结果
  -> 打开结果弹窗
       成功：显示“已复制到剪切板”与完整原文
       失败：显示“复制失败”、完整原文和恢复动作
```

### 再次复制

- 用户点击“再次复制”或“重试复制”后，按钮进入加载态并暂时禁用。
- 成功后在当前弹窗内更新为成功状态，不叠加新弹窗。
- 失败后在当前弹窗内保留失败状态和原文。
- 快速重复点击不得并发触发多次剪贴板写入。

### 空内容

- 操作指引加载命令期间，复制按钮禁用。
- 命令生成接口返回空字符串或仅空白内容时，不显示成功状态。
- 弹窗显示“复制失败”以及“未获取到可复制内容”，不提供对空内容的重试复制；用户可关闭后重新获取命令。

### 关闭

- 支持“知道了”、右上角关闭按钮和 Esc。
- 关闭后清除当前弹窗保存的原文与状态。
- 弹窗关闭不影响原页面、已生成命令和安装流程状态。

## 视觉与可访问性

- 桌面端宽度约 680px，小视口下遵循 Ant Design Modal 自适应边距。
- 原文区域最大高度约 240px，超出后在代码区域内滚动。
- 保留原文的换行、空格和所有字符，不截断、不省略、不改写。
- 使用等宽字体展示原文；允许横向和纵向滚动，避免自动折行改变命令的视觉结构。
- 成功与失败同时使用图标和文字，不只依赖颜色。
- “知道了”为主按钮；“再次复制/重试复制”为次按钮。
- 打开弹窗后保持合理的键盘焦点顺序；关闭后焦点回到触发按钮。
- 加载中按钮具有明确的 `loading` 和禁用状态。
- 中英文文案均通过节点管理 i18n 提供，不硬编码中文。
- 颜色、圆角、阴影、间距和动效沿用现有 Ant Design 与项目主题变量。

## 入口接入

### 控制器操作指引

- 主安装命令复制接入统一结果弹窗。
- 命令加载中或内容为空时禁止显示成功。
- 调试字段与 Artifact JSON 继续使用轻提示。

### 控制器安装进度页

- 点击“复制安装命令”后先调用现有命令生成接口。
- 接口成功且返回非空内容后进入真实剪贴板写入流程。
- 接口请求失败时沿用请求层错误反馈，不伪装为剪贴板失败。
- 空响应进入明确的空内容错误状态。

### 云区域环境

- 已生成的代理部署脚本接入统一结果弹窗。
- 移除复制后无条件打开“复制成功”确认框的行为。
- 原弹窗中的“刷新代理状态”不再绑定在复制成功反馈内；用户仍通过页面现有状态刷新入口完成刷新，避免把“已复制”和“已执行”混为一谈。

## 错误语义

需要区分：

1. 命令生成失败：未获得原文，由请求层反馈。
2. 命令内容为空：获得了无效原文，弹窗提示未获取到可复制内容。
3. 剪贴板写入失败：原文有效但浏览器拒绝写入，弹窗展示原文、失败原因方向和重试动作。
4. 复制成功：浏览器确认写入完成，才显示成功状态。

不得将“已展示原文”等同于“已复制”，也不得将“已复制”描述为“命令已执行”。

## 安全与隐私

- 安装命令可能包含会话或节点参数，弹窗只展示当前调用方已经获得的原文。
- 不将原文写入日志、埋点、审计事件、本地存储或项目状态持久层。
- 不在错误上报中附带复制原文。
- 关闭弹窗时清理 Hook 内保存的原文。
- 不增加命令编辑能力，防止结果弹窗成为任意脚本编辑入口。

## 测试与验收

### 剪贴板工具测试

- Clipboard API 成功时返回成功。
- Clipboard API Promise 拒绝时返回失败，不触发成功反馈。
- Clipboard API 不可用时进入兼容分支。
- `execCommand('copy')` 返回 `true` 时成功。
- `execCommand('copy')` 返回 `false` 或抛错时失败。
- 兼容分支无论成功失败都清理临时 `textarea`。
- 空字符串和仅空白字符串不执行剪贴板写入。

### 状态与弹窗测试

- 首次复制成功后展示成功状态和完整原文。
- 首次复制失败后展示失败状态、完整原文和重试动作。
- 再次复制期间按钮显示加载且不可重复触发。
- 再次复制结果只更新当前弹窗，不创建叠加弹窗。
- 空内容不会展示“已复制到剪切板”。
- 关闭弹窗后清除原文与状态。

### 入口测试

- 控制器操作指引主命令使用统一结果弹窗，调试字段仍为轻提示。
- 控制器安装进度页等待命令接口返回后再复制。
- 云区域代理部署脚本复制成功和失败均使用统一结果弹窗。
- 三个入口不再无条件显示成功反馈。

### 质量门禁

- 新增节点管理命令复制专项测试脚本并加入 `web/package.json`。
- 运行专项测试。
- 对触及文件运行 ESLint。
- 运行 `NEXTAPI_INSTALL_APP=node-manager pnpm precommit` 和 TypeScript 检查。
- 若全量 `pnpm lint` 或 `pnpm type-check` 被任务外既有问题阻断，记录阻断项，并保留专项测试与触及文件检查证据。

## 验收场景

1. 浏览器允许剪贴板写入时，点击三个目标入口中的任意一个，弹窗显示“已复制到剪切板”，原文与实际传入剪贴板的字符串完全一致。
2. 浏览器拒绝剪贴板写入时，不出现成功状态；弹窗显示失败状态和完整原文，用户可以重试或手动选择。
3. 命令接口返回空内容时，不执行剪贴板写入，不显示成功状态。
4. 长命令在弹窗代码区域内完整可查看，不撑高整个页面、不被截断。
5. 用户通过键盘可以触发复制、遍历弹窗按钮并关闭弹窗。
6. 复制内容不会出现在日志、本地存储或错误上报中。

## 已确认决策

- 覆盖节点管理全部命令/脚本复制入口，不扩展到普通内容复制。
- 采用标准确认弹窗布局，贴近现有 Ant Design UI。
- 采用共享 `useCommandCopyDialog`，不做逐页重复实现或全局 Provider。
- 成功和失败均展示原文，但只有真实写入成功才显示“已复制到剪切板”。
- 云区域脚本复制反馈不再把“刷新代理状态”与“已复制”绑定，避免复制与执行状态混淆。
