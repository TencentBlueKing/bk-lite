# 节点管理命令复制结果弹窗实施计划

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
