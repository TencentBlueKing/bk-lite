# 三模块交互统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全量统一运营分析、告警、CMDB 三个模块的说明文案、工具栏、表格、表单、弹窗/抽屉、长文本和宽高自适应交互，同时保留资产搜索、宽表、画布、大屏、拓扑、3D 等特殊页面场景。

**Architecture:** 先补齐可验证基线和静态扫描脚本，再在 `web/src/components` 增加薄的共享交互组件，最后按页面类型迁移三模块。普通解释统一 Tooltip，风险/错误/空状态/校验保持显式展示。

**Tech Stack:** Next.js 16、React 19、TypeScript、Ant Design 5、Tailwind、SCSS Modules、react-intl、pnpm。

## Global Constraints

- 工作目录固定为 `/Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification`。
- 只改 `web/` 和本计划关联的 `docs/superpowers/*`，不改 server/mobile/webchat。
- 全量覆盖 `web/src/app/ops-analysis`、`web/src/app/alarm`、`web/src/app/cmdb`。
- 不为了统一而统一：特殊页面保留原有场景体验，只修 token、i18n、响应式、overflow、resize 安全边界。
- 普通解释说明优先 Tooltip；风险、错误、空状态、校验、不可逆操作不藏 Tooltip。
- 新增文案必须同时写入 zh/en。
- 页面整体不得出现非预期横向滚动；宽表只允许局部横向滚动。
- Modal/Drawer footer 必须可见，长内容在 body 内滚动。
- 不全仓格式化，不扩大无关 diff。
- 设计文档：`docs/superpowers/specs/2026-07-15-ui-interaction-unification-design.md`。

---

## File Structure

### New Shared Components

- `web/src/components/page-intro/index.tsx`
  - 页面级标题、短说明、说明 Tooltip、可选 extra、可选 compact 统计。
- `web/src/components/page-intro/index.module.scss`
  - 两行说明截断、响应式 header、token 化样式。
- `web/src/components/responsive-action-bar/index.tsx`
  - 左右工具栏、按钮折叠、More 菜单、图标 Tooltip。
- `web/src/components/responsive-action-bar/index.module.scss`
  - wrap、measurement、overflow 安全样式。
- `web/src/components/management-page-shell/index.tsx`
  - 管理页 flex 高度壳、PageIntro + ActionBar + 内容区。
- `web/src/components/safe-text/index.tsx`
  - 单行/多行省略、Tooltip、路径/命令局部滚动模式。
- `web/src/components/form-layout/index.tsx`
  - Modal body 样式、Drawer form 区块、label Tooltip helper。

### New Utilities And Scripts

- `web/src/utils/tableScroll.ts`
  - 管理页表格滚动配置工具。
- `web/scripts/ui-i18n-key-check.ts`
  - zh/en key 对齐检查。
- `web/scripts/ui-text-risk-scan.ts`
  - 英文长度、固定宽高、overflow 风险扫描。
- `web/scripts/ui-shell-components-test.ts`
  - 共享组件纯函数和渲染结构轻量测试。

### Modified Module Files

- Ops Analysis:
  - `web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx`
  - `web/src/app/ops-analysis/(pages)/settings/namespace/page.tsx`
  - `web/src/app/ops-analysis/(pages)/view/components/viewWorkspace.tsx`
  - `web/src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardToolbar.tsx`
  - `web/src/app/ops-analysis/(pages)/view/topology/components/toolbar.tsx`
  - `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx`
  - `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx`
  - `web/src/app/ops-analysis/locales/zh.json`
  - `web/src/app/ops-analysis/locales/en.json`

- Alarm:
  - `web/src/app/alarm/components/introduction/index.tsx`
  - `web/src/app/alarm/(pages)/alarms/page.tsx`
  - `web/src/app/alarm/(pages)/incidents/page.tsx`
  - `web/src/app/alarm/(pages)/integration/page.tsx`
  - `web/src/app/alarm/(pages)/settings/actionRules/page.tsx`
  - `web/src/app/alarm/(pages)/settings/correlationRules/page.tsx`
  - `web/src/app/alarm/(pages)/settings/alertAssign/page.tsx`
  - `web/src/app/alarm/(pages)/settings/alertEnrichment/page.tsx`
  - `web/src/app/alarm/(pages)/settings/shieldStrategy/page.tsx`
  - `web/src/app/alarm/(pages)/settings/globalConfig/page.tsx`
  - `web/src/app/alarm/locales/zh.json`
  - `web/src/app/alarm/locales/en.json`

- CMDB:
  - `web/src/app/cmdb/components/introduction/index.tsx`
  - `web/src/app/cmdb/(pages)/assetData/page.tsx`
  - `web/src/app/cmdb/(pages)/assetData/index.module.scss`
  - `web/src/app/cmdb/(pages)/assetSearch/page.tsx`
  - `web/src/app/cmdb/(pages)/assetSearch/landing.tsx`
  - `web/src/app/cmdb/(pages)/assetSearch/index.module.scss`
  - `web/src/app/cmdb/(pages)/assetManage/management/page.tsx`
  - `web/src/app/cmdb/(pages)/assetManage/management/index.module.scss`
  - `web/src/app/cmdb/(pages)/assetManage/operationLog/page.tsx`
  - `web/src/app/cmdb/(pages)/assetManage/customReporting/page.tsx`
  - `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx`
  - `web/src/app/cmdb/components/subscription/subscriptionDrawer.tsx`
  - `web/src/app/cmdb/components/subscription/subscriptionRuleForm.tsx`
  - `web/src/app/cmdb/locales/zh.json`
  - `web/src/app/cmdb/locales/en.json`

---

### Task 1: Stabilize Three-App Type-Check Baseline

**Files:**
- Modify: `web/package.json`
- Modify: `web/src/app/alarm/api/incidents.ts`
- Modify: `web/src/app/alarm/(pages)/alarms/components/relatedAlertsPanel.tsx`

**Interfaces:**
- Produces: `NEXTAPI_INSTALL_APP=ops-analysis,alarm,cmdb pnpm type-check` reaches only business errors introduced by later tasks.
- Consumes: existing imports from ops-analysis, alarm, cmdb.

- [ ] **Step 1: Record current baseline output**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
NEXTAPI_INSTALL_APP=ops-analysis,alarm,cmdb pnpm type-check
```

Expected: FAIL with missing modules including `react-activation`, `@dnd-kit/core`, `@antv/xflow`, `zustand`, `gridstack`, `three`, and existing alarm type errors.

- [ ] **Step 2: Add missing runtime dependencies**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
pnpm add react-activation @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities @antv/xflow zustand gridstack three @types/three react-masonry-css @isoflow/isopacks x-isoflow-react-19
```

Expected: `package.json` and `pnpm-lock.yaml` update.

- [ ] **Step 3: Fix incident delete API import**

Open `web/src/app/alarm/api/incidents.ts`. Replace the undefined `del(...)` call with the request client's delete method already used in neighboring API files. The expected shape is:

```ts
const { get, post, put, del } = useApiClient();
```

If the local `useApiClient()` destructuring uses a different alias, match `web/src/app/alarm/api/alarms.ts` exactly.

- [ ] **Step 4: Fix related alert type conversion**

Open `web/src/app/alarm/(pages)/alarms/components/relatedAlertsPanel.tsx`. Replace direct conversion from `RelatedAlertItem` to `AlarmTableDataItem` with a safe mapper:

```ts
const toAlarmTableRow = (item: RelatedAlertItem): Partial<AlarmTableDataItem> & RelatedAlertItem => ({
  ...item,
  event_count: item.event_count ?? 0,
  source_names: item.source_names ?? [],
  duration: item.duration ?? '--',
  operator_user: item.operator_user ?? '',
});
```

Use `toAlarmTableRow(record)` where the table action expects alarm-style data.

- [ ] **Step 5: Verify baseline**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
NEXTAPI_INSTALL_APP=ops-analysis,alarm,cmdb pnpm type-check
```

Expected: PASS, or FAIL only on `@isoflow/*` type gaps. If `@isoflow/*` remains type-only blocked, add a local declaration file:

```ts
// web/src/types/isoflow.d.ts
declare module '@isoflow/isopacks/dist/utils';
declare module '@isoflow/isopacks/dist/aws';
declare module '@isoflow/isopacks/dist/gcp';
declare module '@isoflow/isopacks/dist/azure';
declare module '@isoflow/isopacks/dist/isoflow';
declare module '@isoflow/isopacks/dist/kubernetes';
declare module 'x-isoflow-react-19';
```

Then rerun the command and expect PASS.

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/pnpm-lock.yaml web/src/app/alarm/api/incidents.ts web/src/app/alarm/(pages)/alarms/components/relatedAlertsPanel.tsx web/src/types/isoflow.d.ts
git commit -m "chore: stabilize three app frontend baseline"
```

### Task 2: Add Static UI Risk Scanners

**Files:**
- Create: `web/scripts/ui-i18n-key-check.ts`
- Create: `web/scripts/ui-text-risk-scan.ts`
- Modify: `web/package.json`

**Interfaces:**
- Produces: `pnpm test:ui-i18n-keys`
- Produces: `pnpm test:ui-text-risk`

- [ ] **Step 1: Add locale key checker**

Create `web/scripts/ui-i18n-key-check.ts`:

```ts
import fs from 'node:fs';
import path from 'node:path';

const apps = ['ops-analysis', 'alarm', 'cmdb'];

const flatten = (
  value: unknown,
  prefix = '',
  output: Record<string, string> = {}
): Record<string, string> => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    Object.entries(value as Record<string, unknown>).forEach(([key, child]) => {
      flatten(child, prefix ? `${prefix}.${key}` : key, output);
    });
    return output;
  }
  output[prefix] = String(value ?? '');
  return output;
};

let failed = false;

apps.forEach((app) => {
  const dir = path.join(process.cwd(), 'src/app', app, 'locales');
  const zh = flatten(JSON.parse(fs.readFileSync(path.join(dir, 'zh.json'), 'utf8')));
  const en = flatten(JSON.parse(fs.readFileSync(path.join(dir, 'en.json'), 'utf8')));
  const zhOnly = Object.keys(zh).filter((key) => !(key in en));
  const enOnly = Object.keys(en).filter((key) => !(key in zh));

  if (zhOnly.length || enOnly.length) {
    failed = true;
    console.error(`[${app}] locale keys mismatch`);
    if (zhOnly.length) console.error(`  zh only: ${zhOnly.join(', ')}`);
    if (enOnly.length) console.error(`  en only: ${enOnly.join(', ')}`);
  } else {
    console.log(`[${app}] locale keys aligned (${Object.keys(zh).length})`);
  }
});

if (failed) process.exit(1);
```

- [ ] **Step 2: Add text and layout risk scanner**

Create `web/scripts/ui-text-risk-scan.ts`:

```ts
import fs from 'node:fs';
import path from 'node:path';

const apps = ['ops-analysis', 'alarm', 'cmdb'];
const sourceExt = new Set(['.ts', '.tsx', '.scss', '.css']);
const ignored = new Set(['node_modules', 'public']);

const walk = (dir: string, files: string[] = []): string[] => {
  fs.readdirSync(dir, { withFileTypes: true }).forEach((entry) => {
    if (ignored.has(entry.name)) return;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, files);
    if (entry.isFile() && sourceExt.has(path.extname(entry.name))) files.push(full);
  });
  return files;
};

const riskyPattern =
  /(minWidth|min-width|width:\s*['"]?\d|height:\s*['"]?\d|calc\(100vh|calc\(100vw|overflow:\s*hidden|overflow-hidden|scroll=\{\{\s*x|white-space:\s*nowrap|whitespace-nowrap|w-\[|h-\[)/g;

apps.forEach((app) => {
  const root = path.join(process.cwd(), 'src/app', app);
  const files = walk(root);
  const rows = files.flatMap((file) => {
    const text = fs.readFileSync(file, 'utf8');
    const hits = [...text.matchAll(riskyPattern)];
    return hits.length
      ? [{ file: path.relative(process.cwd(), file), count: hits.length }]
      : [];
  });

  rows.sort((a, b) => b.count - a.count);
  console.log(`\n[${app}] layout/text risk files: ${rows.length}`);
  rows.slice(0, 30).forEach((row) => {
    console.log(`${String(row.count).padStart(4)} ${row.file}`);
  });
});
```

- [ ] **Step 3: Wire scripts**

Modify `web/package.json` scripts:

```json
{
  "test:ui-i18n-keys": "pnpm exec tsx scripts/ui-i18n-key-check.ts",
  "test:ui-text-risk": "pnpm exec tsx scripts/ui-text-risk-scan.ts"
}
```

- [ ] **Step 4: Verify scanner baseline**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
pnpm test:ui-i18n-keys
pnpm test:ui-text-risk
```

Expected: i18n key check FAILS before Task 3 because CMDB locale keys are mismatched; risk scan prints ranked files and exits 0.

- [ ] **Step 5: Commit**

```bash
git add web/scripts/ui-i18n-key-check.ts web/scripts/ui-text-risk-scan.ts web/package.json
git commit -m "test: add ui consistency scanners"
```

### Task 3: Align Three-App Locale Keys

**Files:**
- Modify: `web/src/app/cmdb/locales/zh.json`
- Modify: `web/src/app/cmdb/locales/en.json`
- Modify: `web/src/app/alarm/locales/zh.json`
- Modify: `web/src/app/alarm/locales/en.json`

**Interfaces:**
- Consumes: `pnpm test:ui-i18n-keys` from Task 2.
- Produces: aligned locale keys for three modules.

- [ ] **Step 1: Run key checker**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
pnpm test:ui-i18n-keys
```

Expected: FAIL listing CMDB zh-only/en-only keys and alarm `alarms.remain` / `alarms.remaining` mismatch.

- [ ] **Step 2: Fix alarm key mismatch**

Open `web/src/app/alarm/locales/zh.json` and `web/src/app/alarm/locales/en.json`. Use a single key:

```json
"alarms.remaining": "剩余"
```

```json
"alarms.remaining": "Remaining"
```

Search source for `alarms.remain` and replace with `alarms.remaining`.

- [ ] **Step 3: Fill CMDB missing English keys**

For every zh-only key reported by `pnpm test:ui-i18n-keys`, add an English value to `web/src/app/cmdb/locales/en.json`. Use concise operational English. Example entries:

```json
"FilterBar.savedFilters_abbreviation": "Saved filters",
"FilterBar.saveFailed": "Failed to save",
"FilterBar.deleteFailed": "Failed to delete",
"Model.systemConstraints": "System constraints",
"Model.systemConstraintsDescription": "These constraints are enforced by the system and cannot be changed here.",
"Model.fieldBehavior": "Field behavior",
"Model.unsupported": "Unsupported"
```

Preserve existing JSON nesting style.

- [ ] **Step 4: Fill CMDB missing Chinese keys**

For every en-only key reported by the checker, add a Chinese value to `web/src/app/cmdb/locales/zh.json`. Example entries:

```json
"FilterBar.cancel": "取消",
"FilterBar.confirm": "确认",
"Collection.password": "密码",
"Collection.sslVerify": "SSL 校验"
```

- [ ] **Step 5: Verify**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
pnpm test:ui-i18n-keys
```

Expected: PASS for ops-analysis, alarm, cmdb.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/cmdb/locales/zh.json web/src/app/cmdb/locales/en.json web/src/app/alarm/locales/zh.json web/src/app/alarm/locales/en.json
git commit -m "fix: align ui locale keys"
```

### Task 4: Build Shared Text And Explanation Components

**Files:**
- Create: `web/src/components/safe-text/index.tsx`
- Create: `web/src/components/page-intro/index.tsx`
- Create: `web/src/components/page-intro/index.module.scss`
- Create: `web/scripts/ui-shell-components-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Produces: `SafeText(props: SafeTextProps): JSX.Element`
- Produces: `PageIntro(props: PageIntroProps): JSX.Element`
- Produces: `pnpm test:ui-shell-components`

- [ ] **Step 1: Create SafeText**

Create `web/src/components/safe-text/index.tsx`:

```tsx
'use client';

import React from 'react';
import { Tooltip } from 'antd';

export interface SafeTextProps {
  text?: React.ReactNode;
  tooltip?: React.ReactNode;
  className?: string;
  mode?: 'single' | 'multi' | 'wrap' | 'code';
  lines?: 1 | 2 | 3;
  title?: string;
}

const lineClampClass: Record<1 | 2 | 3, string> = {
  1: 'line-clamp-1',
  2: 'line-clamp-2',
  3: 'line-clamp-3',
};

const SafeText: React.FC<SafeTextProps> = ({
  text,
  tooltip,
  className = '',
  mode = 'single',
  lines = 1,
  title,
}) => {
  const content = text ?? '--';
  const tooltipContent = tooltip ?? (typeof content === 'string' ? content : title);
  const baseClass =
    mode === 'code'
      ? 'block max-w-full overflow-x-auto whitespace-pre font-mono text-xs'
      : mode === 'wrap'
        ? 'break-words'
        : mode === 'multi'
          ? `${lineClampClass[lines]} break-words`
          : 'block max-w-full truncate';

  const node = <span className={`${baseClass} ${className}`}>{content}</span>;

  if (!tooltipContent) return node;

  return (
    <Tooltip title={tooltipContent}>
      {node}
    </Tooltip>
  );
};

export default SafeText;
```

- [ ] **Step 2: Create PageIntro**

Create `web/src/components/page-intro/index.tsx`:

```tsx
'use client';

import React from 'react';
import { Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import SafeText from '@/components/safe-text';
import styles from './index.module.scss';

export interface PageIntroProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  extra?: React.ReactNode;
  className?: string;
  compact?: boolean;
  stats?: Array<{ label: React.ReactNode; value: React.ReactNode }>;
}

const PageIntro: React.FC<PageIntroProps> = ({
  title,
  description,
  extra,
  className = '',
  compact = false,
  stats = [],
}) => (
  <section className={`${styles.pageIntro} ${compact ? styles.compact : ''} ${className}`}>
    <div className={styles.main}>
      <div className={styles.titleRow}>
        <h1>{title}</h1>
        {description && (
          <Tooltip title={description}>
            <InfoCircleOutlined className={styles.infoIcon} aria-label="description" />
          </Tooltip>
        )}
      </div>
      {description && (
        <SafeText
          text={description}
          tooltip={description}
          mode="multi"
          lines={2}
          className={styles.description}
        />
      )}
      {stats.length > 0 && (
        <div className={styles.stats}>
          {stats.map((item, index) => (
            <div key={index} className={styles.statItem}>
              <SafeText text={item.label} className={styles.statLabel} />
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
    {extra && <div className={styles.extra}>{extra}</div>}
  </section>
);

export default PageIntro;
```

- [ ] **Step 3: Add PageIntro styles**

Create `web/src/components/page-intro/index.module.scss`:

```scss
.pageIntro {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--color-border-1);
  border-radius: 8px;
  background: var(--color-bg-1);
}

.compact {
  padding: 12px 16px;
}

.main {
  min-width: 0;
  flex: 1;
}

.titleRow {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;

  h1 {
    min-width: 0;
    margin: 0;
    overflow: hidden;
    color: var(--color-text-1);
    font-size: 16px;
    font-weight: 600;
    line-height: 24px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.infoIcon {
  flex: 0 0 auto;
  color: var(--color-text-3);
}

.description {
  margin-top: 4px;
  color: var(--color-text-3);
  font-size: 13px;
  line-height: 20px;
}

.extra {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
  max-width: 100%;
}

.stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.statItem {
  min-width: 120px;
  max-width: 220px;
  padding: 8px 10px;
  border: 1px solid var(--color-border-1);
  border-radius: 6px;
  background: var(--color-fill-1);

  strong {
    display: block;
    margin-top: 2px;
    color: var(--color-text-1);
    font-size: 14px;
  }
}

.statLabel {
  color: var(--color-text-3);
  font-size: 12px;
}

@media (max-width: 768px) {
  .pageIntro {
    flex-direction: column;
  }

  .extra {
    width: 100%;
    flex-wrap: wrap;
  }
}
```

- [ ] **Step 4: Add shell component test**

Create `web/scripts/ui-shell-components-test.ts`:

```ts
import fs from 'node:fs';
import path from 'node:path';

const files = [
  'src/components/safe-text/index.tsx',
  'src/components/page-intro/index.tsx',
  'src/components/page-intro/index.module.scss',
];

files.forEach((file) => {
  const full = path.join(process.cwd(), file);
  if (!fs.existsSync(full)) {
    throw new Error(`${file} is missing`);
  }
});

const pageIntro = fs.readFileSync(path.join(process.cwd(), files[1]), 'utf8');
if (!pageIntro.includes('InfoCircleOutlined')) {
  throw new Error('PageIntro must expose description through a tooltip icon');
}
if (!pageIntro.includes('SafeText')) {
  throw new Error('PageIntro must use SafeText for long descriptions');
}

const styles = fs.readFileSync(path.join(process.cwd(), files[2]), 'utf8');
if (styles.includes('min-width: 800px')) {
  throw new Error('PageIntro must not use fixed minimum widths');
}

console.log('ui shell components smoke test passed');
```

- [ ] **Step 5: Wire script**

Modify `web/package.json`:

```json
{
  "test:ui-shell-components": "pnpm exec tsx scripts/ui-shell-components-test.ts"
}
```

- [ ] **Step 6: Verify**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
pnpm test:ui-shell-components
```

Expected: `ui shell components smoke test passed`.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/safe-text web/src/components/page-intro web/scripts/ui-shell-components-test.ts web/package.json
git commit -m "feat: add shared page intro and safe text"
```

### Task 5: Build Shared Layout And Action Components

**Files:**
- Create: `web/src/components/responsive-action-bar/index.tsx`
- Create: `web/src/components/responsive-action-bar/index.module.scss`
- Create: `web/src/components/management-page-shell/index.tsx`
- Create: `web/src/components/form-layout/index.tsx`
- Create: `web/src/utils/tableScroll.ts`
- Modify: `web/scripts/ui-shell-components-test.ts`

**Interfaces:**
- Produces: `ResponsiveActionBar`
- Produces: `ManagementPageShell`
- Produces: `modalBodyScrollStyles`
- Produces: `getTableScrollY(offset: number): string`

- [ ] **Step 1: Create ResponsiveActionBar**

Create `web/src/components/responsive-action-bar/index.tsx`:

```tsx
'use client';

import React from 'react';
import { Button, Dropdown, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { MoreOutlined } from '@ant-design/icons';
import styles from './index.module.scss';

export interface ResponsiveActionItem {
  key: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  danger?: boolean;
  disabled?: boolean;
  loading?: boolean;
  primary?: boolean;
  tooltip?: React.ReactNode;
  onClick?: () => void;
}

export interface ResponsiveActionBarProps {
  left?: React.ReactNode;
  right?: React.ReactNode;
  actions?: ResponsiveActionItem[];
  moreLabel?: React.ReactNode;
  className?: string;
}

const ResponsiveActionBar: React.FC<ResponsiveActionBarProps> = ({
  left,
  right,
  actions = [],
  moreLabel = 'More',
  className = '',
}) => {
  const visibleActions = actions.slice(0, 2);
  const overflowActions = actions.slice(2);
  const menu: MenuProps = {
    items: overflowActions.map((item) => ({
      key: item.key,
      label: item.label,
      icon: item.icon,
      danger: item.danger,
      disabled: item.disabled,
      onClick: item.onClick,
    })),
  };

  return (
    <div className={`${styles.actionBar} ${className}`}>
      <div className={styles.left}>{left}</div>
      <div className={styles.right}>
        {right}
        {visibleActions.map((item) => {
          const button = (
            <Button
              key={item.key}
              type={item.primary ? 'primary' : 'default'}
              danger={item.danger}
              disabled={item.disabled}
              loading={item.loading}
              icon={item.icon}
              onClick={item.onClick}
            >
              {item.label}
            </Button>
          );
          return item.tooltip ? (
            <Tooltip key={item.key} title={item.tooltip}>{button}</Tooltip>
          ) : button;
        })}
        {overflowActions.length > 0 && (
          <Dropdown menu={menu} placement="bottomRight">
            <Button icon={<MoreOutlined />}>{moreLabel}</Button>
          </Dropdown>
        )}
      </div>
    </div>
  );
};

export default ResponsiveActionBar;
```

- [ ] **Step 2: Add ResponsiveActionBar styles**

Create `web/src/components/responsive-action-bar/index.module.scss`:

```scss
.actionBar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-width: 0;
}

.left {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.right {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  max-width: 100%;
}

@media (max-width: 1024px) {
  .actionBar {
    flex-direction: column;
  }

  .right {
    width: 100%;
    justify-content: flex-start;
  }
}
```

- [ ] **Step 3: Create ManagementPageShell**

Create `web/src/components/management-page-shell/index.tsx`:

```tsx
'use client';

import React from 'react';
import PageIntro from '@/components/page-intro';

export interface ManagementPageShellProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  introExtra?: React.ReactNode;
  actionBar?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
}

const ManagementPageShell: React.FC<ManagementPageShellProps> = ({
  title,
  description,
  introExtra,
  actionBar,
  children,
  className = '',
  contentClassName = '',
}) => (
  <div className={`flex h-full min-h-0 w-full flex-col gap-4 overflow-hidden ${className}`}>
    <PageIntro title={title} description={description} extra={introExtra} />
    {actionBar && <div className="shrink-0">{actionBar}</div>}
    <div className={`min-h-0 flex-1 overflow-hidden rounded-lg bg-[var(--color-bg-1)] ${contentClassName}`}>
      {children}
    </div>
  </div>
);

export default ManagementPageShell;
```

- [ ] **Step 4: Create form layout helpers**

Create `web/src/components/form-layout/index.tsx`:

```tsx
import React from 'react';
import { Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';

export const modalBodyScrollStyles = {
  body: {
    maxHeight: 'calc(100vh - 240px)',
    overflowY: 'auto' as const,
  },
};

export const drawerBodyScrollStyles = {
  body: {
    paddingBottom: 24,
    overflowY: 'auto' as const,
  },
};

export const LabelWithTooltip: React.FC<{
  label: React.ReactNode;
  tooltip?: React.ReactNode;
}> = ({ label, tooltip }) => (
  <span className="inline-flex min-w-0 items-center gap-1">
    <span className="min-w-0 truncate">{label}</span>
    {tooltip && (
      <Tooltip title={tooltip}>
        <InfoCircleOutlined className="shrink-0 text-[var(--color-text-3)]" />
      </Tooltip>
    )}
  </span>
);
```

- [ ] **Step 5: Create table scroll helper**

Create `web/src/utils/tableScroll.ts`:

```ts
export const getTableScrollY = (offset: number): string =>
  `max(240px, calc(100vh - ${offset}px))`;

export const getWideTableScrollX = (minWidth: number): { x: number } => ({
  x: minWidth,
});
```

- [ ] **Step 6: Extend smoke test**

Append to `web/scripts/ui-shell-components-test.ts`:

```ts
[
  'src/components/responsive-action-bar/index.tsx',
  'src/components/management-page-shell/index.tsx',
  'src/components/form-layout/index.tsx',
  'src/utils/tableScroll.ts',
].forEach((file) => {
  const full = path.join(process.cwd(), file);
  if (!fs.existsSync(full)) throw new Error(`${file} is missing`);
});
```

- [ ] **Step 7: Verify**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
pnpm test:ui-shell-components
```

Expected: `ui shell components smoke test passed`.

- [ ] **Step 8: Commit**

```bash
git add web/src/components/responsive-action-bar web/src/components/management-page-shell web/src/components/form-layout web/src/utils/tableScroll.ts web/scripts/ui-shell-components-test.ts
git commit -m "feat: add shared management layout primitives"
```

### Task 6: Migrate Ops Analysis Management And Toolbar Surfaces

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/settings/namespace/page.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/components/viewWorkspace.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardToolbar.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/components/toolbar.tsx`
- Modify: `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx`
- Modify: `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx`

**Interfaces:**
- Consumes: `PageIntro`, `ManagementPageShell`, `ResponsiveActionBar`, `SafeText`, `modalBodyScrollStyles`, `getTableScrollY`.
- Produces: ops-analysis settings and view toolbar aligned with shared primitives.

- [ ] **Step 1: Wrap data source page**

In `dataSource/page.tsx`, replace the top AntD `Card` intro and manual toolbar with:

```tsx
<ManagementPageShell
  title={t('dataSource.introTitle')}
  description={t('dataSource.introMsg')}
  actionBar={(
    <ResponsiveActionBar
      left={(
        <Input
          allowClear
          value={searchValue}
          placeholder={t('common.search')}
          style={{ width: 250, maxWidth: '100%' }}
          onChange={(e) => setSearchValue(e.target.value)}
          onPressEnter={(e) => handleFilter(e.currentTarget.value)}
          onClear={() => {
            setSearchValue('');
            handleFilter('');
          }}
        />
      )}
      actions={[
        {
          key: 'import',
          label: t('common.import'),
          icon: <UploadOutlined />,
          onClick: () => setImportModalVisible(true),
        },
        {
          key: 'add',
          label: t('common.addNew'),
          primary: true,
          onClick: () => handleEdit('add'),
        },
      ]}
    />
  )}
>
  <CustomTable ... />
</ManagementPageShell>
```

Keep existing permission wrappers by wrapping action labels or rendering `right` content where permission logic is needed.

- [ ] **Step 2: Use table scroll helper**

In ops-analysis settings tables, replace:

```tsx
scroll={{ y: 'calc(100vh - 430px)' }}
```

with:

```tsx
scroll={{ y: getTableScrollY(430) }}
```

Import:

```ts
import { getTableScrollY } from '@/utils/tableScroll';
```

- [ ] **Step 3: Keep ViewWorkspace compact but safer**

In `viewWorkspace.tsx`, replace hard-coded `contentClassName = 'bg-[#f7f8fa]'` with:

```tsx
contentClassName = 'bg-[var(--color-bg-2)]'
```

Use `SafeText` for `selectedItem.name` and `resolvedDescription`:

```tsx
<SafeText text={selectedItem.name || titleFallback} className="text-base font-semibold leading-6 text-[var(--color-text-1)]" />
<SafeText text={resolvedDescription} mode="multi" lines={2} className="text-xs leading-4 text-[var(--color-text-3)]" />
```

- [ ] **Step 4: Normalize toolbar icon buttons**

In dashboard and topology toolbars, replace inline icon styles:

```tsx
icon={<ReloadOutlined style={{ fontSize: 16 }} />}
```

with:

```tsx
icon={<ReloadOutlined aria-hidden="true" />}
```

Use a shared class:

```ts
const iconButtonClassName = 'rounded-full! h-8 w-8 min-w-8 flex items-center justify-center';
```

Replace selected state hard-coded colors:

```tsx
style={{
  backgroundColor: isSelectMode ? 'var(--color-primary-bg-active)' : 'transparent',
  color: isSelectMode ? 'var(--color-primary)' : undefined,
}}
```

- [ ] **Step 5: Make UnifiedFilterBar long text safe**

In `unifiedFilterBar.tsx`, wrap labels:

```tsx
<SafeText
  text={`${definition.name}:`}
  tooltip={definition.name}
  className="max-w-[160px] text-xs font-medium text-(--color-text-2)"
/>
```

Set control styles:

```tsx
style={{ minWidth: 160, maxWidth: 260 }}
```

Ensure the button group can wrap:

```tsx
className="flex shrink-0 flex-wrap items-center gap-2"
```

- [ ] **Step 6: Apply Modal body scroll in filter config**

In `unifiedFilterConfigModal.tsx`, add:

```tsx
import { modalBodyScrollStyles, LabelWithTooltip } from '@/components/form-layout';
```

Pass:

```tsx
styles={modalBodyScrollStyles}
```

Use `LabelWithTooltip` for long configuration labels with existing explanatory text.

- [ ] **Step 7: Verify ops-analysis**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
NEXTAPI_INSTALL_APP=ops-analysis pnpm type-check
pnpm test:ui-text-risk
```

Expected: type-check PASS after Task 1; risk scan still reports files but no new top risk from modified settings pages.

- [ ] **Step 8: Commit**

```bash
git add web/src/app/ops-analysis web/src/utils/tableScroll.ts
git commit -m "feat: align ops analysis interaction surfaces"
```

### Task 7: Migrate Alarm Pages And Settings

**Files:**
- Modify: `web/src/app/alarm/components/introduction/index.tsx`
- Modify: `web/src/app/alarm/(pages)/alarms/page.tsx`
- Modify: `web/src/app/alarm/(pages)/alarms/index.module.scss`
- Modify: `web/src/app/alarm/(pages)/incidents/page.tsx`
- Modify: `web/src/app/alarm/(pages)/incidents/index.module.scss`
- Modify: `web/src/app/alarm/(pages)/integration/page.tsx`
- Modify: `web/src/app/alarm/(pages)/settings/actionRules/page.tsx`
- Modify: `web/src/app/alarm/(pages)/settings/correlationRules/page.tsx`
- Modify: `web/src/app/alarm/(pages)/settings/alertAssign/page.tsx`
- Modify: `web/src/app/alarm/(pages)/settings/alertEnrichment/page.tsx`
- Modify: `web/src/app/alarm/(pages)/settings/shieldStrategy/page.tsx`
- Modify: `web/src/app/alarm/(pages)/settings/globalConfig/page.tsx`

**Interfaces:**
- Consumes: shared components from Tasks 4 and 5.
- Produces: alarm pages with unified intro, action bars, Tooltip explanations, safer table heights.

- [ ] **Step 1: Replace Introduction implementation**

In `web/src/app/alarm/components/introduction/index.tsx`, replace AntD Card wrapper with:

```tsx
'use client';

import React from 'react';
import PageIntro from '@/components/page-intro';

interface IntroductionProp {
  message: string;
  title: string;
}

const Introduction: React.FC<IntroductionProp> = ({ message, title }) => (
  <PageIntro title={title} description={message} compact className="mb-4" />
);

export default Introduction;
```

Remove `style={{ width: '100%', minWidth: '800px' }}`.

- [ ] **Step 2: Fix alarm workbench width**

In `alarms/index.module.scss`, replace:

```scss
width: calc(100vw - 250px);
```

with:

```scss
flex: 1 1 0;
min-width: 0;
```

In the toolbar div with `min-w-[900px]`, remove the min width and use:

```tsx
<div className="flex flex-wrap items-center justify-between gap-3 mb-[16px]">
```

- [ ] **Step 3: Fix incidents workbench width**

In `incidents/index.module.scss`, replace:

```scss
width: calc(100vw - 250px);
```

with:

```scss
flex: 1 1 0;
min-width: 0;
```

In `incidents/page.tsx`, replace input fixed width with:

```tsx
className="w-full max-w-[300px]"
```

Replace table scroll x:

```tsx
scroll={{ y: getTableScrollY(280), x: 980 }}
```

- [ ] **Step 4: Keep integration page special but use PageIntro**

In `integration/page.tsx`, replace the local `<h1>/<p>` header with:

```tsx
<PageIntro
  title={t('integration.overviewTitle')}
  description={t('integration.overviewDesc')}
  compact
  className="mb-5"
/>
```

- [ ] **Step 5: Migrate settings pages to shared shell**

For each alarm settings list page, wrap with:

```tsx
<ManagementPageShell
  title={pageTitle}
  description={pageDescription}
  actionBar={(
    <ResponsiveActionBar
      left={<Input allowClear value={searchKey} placeholder={t('common.search')} style={{ width: 250, maxWidth: '100%' }} ... />}
      actions={[{ key: 'add', label: t('common.addNew'), primary: true, onClick: () => handleEdit('add') }]}
    />
  )}
>
  <CustomTable scroll={{ y: getTableScrollY(440) }} ... />
</ManagementPageShell>
```

Use existing page-specific title and description keys:

- `settings.actionRuleTitle`
- `settings.correlationRules`
- `settings.assignStrategy.title`
- `settings.alertEnrichment`
- `settings.shieldStrategy`
- `settings.globalConfig.title`

- [ ] **Step 6: Normalize explanatory copy**

For labels, icon hints, and table-column explanations in alarm settings, use:

```tsx
<LabelWithTooltip
  label={t('settings.someLabel')}
  tooltip={t('settings.someLabelTip')}
/>
```

Keep delete confirmations and close warnings in `Modal.confirm({ content })`.

- [ ] **Step 7: Verify alarm**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
NEXTAPI_INSTALL_APP=alarm pnpm type-check
pnpm test:ui-i18n-keys
pnpm test:ui-text-risk
```

Expected: type-check PASS after Task 1 and Task 3; scanners PASS/print risk report.

- [ ] **Step 8: Commit**

```bash
git add web/src/app/alarm
git commit -m "feat: align alarm interaction patterns"
```

### Task 8: Migrate CMDB Management And Workbench Pages

**Files:**
- Modify: `web/src/app/cmdb/components/introduction/index.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetData/page.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetData/index.module.scss`
- Modify: `web/src/app/cmdb/(pages)/assetManage/management/page.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetManage/management/index.module.scss`
- Modify: `web/src/app/cmdb/(pages)/assetManage/operationLog/page.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetManage/customReporting/page.tsx`

**Interfaces:**
- Consumes: shared components from Tasks 4 and 5.
- Produces: CMDB core management/workbench pages with safer width/height and unified explanations.

- [ ] **Step 1: Replace CMDB Introduction**

In `web/src/app/cmdb/components/introduction/index.tsx`, use the same implementation as alarm:

```tsx
'use client';

import React from 'react';
import PageIntro from '@/components/page-intro';

interface IntroductionProp {
  message: string;
  title: string;
}

const Introduction: React.FC<IntroductionProp> = ({ message, title }) => (
  <PageIntro title={title} description={message} compact className="mb-4" />
);

export default Introduction;
```

- [ ] **Step 2: Fix assetData left-tree/right-table sizing**

In `assetData/index.module.scss`, replace:

```scss
min-width: 988px;
```

with:

```scss
min-width: 0;
```

Keep the group selector fixed:

```scss
width: 240px;
min-width: 240px;
```

Ensure `.assetData` has:

```scss
min-width: 0;
overflow: hidden;
```

- [ ] **Step 3: Use ResponsiveActionBar in assetData**

In `assetData/page.tsx`, replace the top row custom flex with:

```tsx
<ResponsiveActionBar
  left={(
    <>
      <GroupTreeSelector style={{ width: 200, maxWidth: '100%' }} ... />
      <SearchFilter ... />
      {modelId === 'ip' && <Tag ...>{t('IPAM.conflictFilter')}</Tag>}
      <RefreshIconButton loading={loading} onClick={() => fetchData()} />
    </>
  )}
  right={(
    <Space wrap>
      {/* existing permission-wrapped add/export/more/subscription controls */}
    </Space>
  )}
/>
```

Preserve existing `ResizeObserver` collapse logic if it still provides better button folding than the generic action bar.

- [ ] **Step 4: Make assetData table local-scroll only**

Replace:

```tsx
scroll={{
  x: 'calc(100vw - 400px)',
  y: storeQueryList.length > 0 ? 'calc(100vh - 320px)' : 'calc(100vh - 300px)'
}}
```

with:

```tsx
scroll={{
  x: 1200,
  y: getTableScrollY(storeQueryList.length > 0 ? 320 : 300),
}}
```

- [ ] **Step 5: Wrap model management page**

In `assetManage/management/page.tsx`, keep the model group card layout but replace the outer intro and toolbar with PageIntro + ResponsiveActionBar:

```tsx
<PageIntro title={t('Model.title')} description={t('Model.message')} compact className="mb-4" />
<ResponsiveActionBar
  left={<Input placeholder={t('common.search')} value={searchText} allowClear ... />}
  right={<Space wrap>{/* existing model/group/config buttons */}</Space>}
/>
```

Ensure model cards use `SafeText` for `model_name`, `model_id`, and group names.

- [ ] **Step 6: Fix model card width safety**

In `assetManage/management/index.module.scss`, keep the card grid but ensure it does not force page overflow:

```scss
.modelList {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.modelListItem,
.addModelCard {
  width: auto;
  min-width: 0;
  margin: 0;
}
```

- [ ] **Step 7: Migrate operationLog and customReporting list pages**

Wrap list pages with `ManagementPageShell`, use `ResponsiveActionBar`, `getTableScrollY`, and `SafeText` for long names/status descriptions. Preserve existing action permissions and business modals.

- [ ] **Step 8: Verify CMDB core**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
NEXTAPI_INSTALL_APP=cmdb pnpm type-check
pnpm test:ui-i18n-keys
pnpm test:ui-text-risk
```

Expected: type-check PASS after Task 1 and Task 3; risk scanner still reports special pages but core workbench/management pages drop in ranking.

- [ ] **Step 9: Commit**

```bash
git add web/src/app/cmdb
git commit -m "feat: align cmdb core interaction patterns"
```

### Task 9: Migrate Complex Forms And Drawers

**Files:**
- Modify: `web/src/app/alarm/(pages)/settings/actionRules/components/operateModal.tsx`
- Modify: `web/src/app/alarm/(pages)/settings/correlationRules/components/operateModal.tsx`
- Modify: `web/src/app/alarm/(pages)/settings/alertAssign/components/operateModal.tsx`
- Modify: `web/src/app/cmdb/components/subscription/subscriptionDrawer.tsx`
- Modify: `web/src/app/cmdb/components/subscription/subscriptionRuleForm.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetManage/management/list/modelModal.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetManage/management/detail/attributes/attributesModal.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx`
- Modify: `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx`

**Interfaces:**
- Consumes: `modalBodyScrollStyles`, `drawerBodyScrollStyles`, `LabelWithTooltip`.
- Produces: long forms that keep footer visible and use Tooltip for ordinary explanations.

- [ ] **Step 1: Apply Modal body scroll**

For every AntD Modal with long form content, add:

```tsx
import { modalBodyScrollStyles } from '@/components/form-layout';
```

Then pass:

```tsx
styles={modalBodyScrollStyles}
```

If the Modal already has `styles`, merge body keys:

```tsx
styles={{
  body: {
    ...modalBodyScrollStyles.body,
    paddingTop: 24,
  },
}}
```

- [ ] **Step 2: Apply Drawer body scroll**

For every Drawer with long form content, add:

```tsx
import { drawerBodyScrollStyles } from '@/components/form-layout';
```

Then pass:

```tsx
styles={drawerBodyScrollStyles}
```

- [ ] **Step 3: Convert ordinary field explanations to Tooltip**

Replace inline gray explanatory text beside labels:

```tsx
label={t('settings.someLabel')}
extra={t('settings.someTip')}
```

with:

```tsx
label={<LabelWithTooltip label={t('settings.someLabel')} tooltip={t('settings.someTip')} />}
```

Keep validation text in `rules` and `help`.

- [ ] **Step 4: Preserve risk and errors as explicit content**

For delete, disable, reset, credential, notification, assignment, and rule scope warnings, keep:

```tsx
<Alert type="warning" showIcon message={t('settings.riskTitle')} description={t('settings.riskDesc')} />
```

or:

```tsx
Modal.confirm({
  title: t('common.delConfirm'),
  content: t('common.delConfirmCxt'),
  okButtonProps: { danger: true },
});
```

Do not convert these to Tooltip.

- [ ] **Step 5: Make dynamic rows wrap**

For Form.List rows that use inline input/select/button groups, use:

```tsx
<div className="grid grid-cols-1 gap-2 md:grid-cols-[minmax(160px,1fr)_minmax(180px,1fr)_auto]">
```

This keeps English labels and validation errors from hiding adjacent controls.

- [ ] **Step 6: Verify form surfaces**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
NEXTAPI_INSTALL_APP=ops-analysis,alarm,cmdb pnpm type-check
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/app/alarm web/src/app/cmdb web/src/app/ops-analysis
git commit -m "feat: standardize long form explanations and layout"
```

### Task 10: Harden Special Pages Without Flattening Their Design

**Files:**
- Modify: `web/src/app/cmdb/(pages)/assetSearch/page.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetSearch/landing.tsx`
- Modify: `web/src/app/cmdb/(pages)/assetSearch/index.module.scss`
- Modify: `web/src/app/cmdb/(pages)/assetData/detail/relationships/*`
- Modify: `web/src/app/cmdb/(pages)/assetData/detail/k8sResources/*`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/*`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/*`
- Modify: `web/src/app/ops-analysis/(pages)/view/architecture/*`

**Interfaces:**
- Consumes: `SafeText`, token rules, resize rules from spec.
- Produces: special pages retain character but meet layout safety rules.

- [ ] **Step 1: Limit asset search fixed widths**

In `assetSearch/index.module.scss`, replace fixed `min-width: 500px` search blocks with responsive bounds:

```scss
width: min(100%, 820px);
min-width: 0;
```

Replace hero image pseudo-element `min-width: 565px` with:

```scss
min-width: min(42vw, 565px);
```

- [ ] **Step 2: Tokenize asset search hard colors where ordinary UI**

For text and panel borders, replace hard-coded ordinary UI colors:

```scss
color: var(--color-text-1);
border-color: var(--color-border-1);
background: var(--color-bg-1);
```

Keep decorative hero gradients if they are isolated inside `assetSearch`.

- [ ] **Step 3: Protect asset search text**

In `landing.tsx`, use `SafeText` for:

- recent change target/message,
- followed asset name,
- model pill text,
- category title.

Example:

```tsx
<SafeText text={item.inst_name} tooltip={item.inst_name} className={assetSearchStyle.followedAssetName} />
```

- [ ] **Step 4: Protect relationship and topology pages**

For CMDB relationship/topology/K8s pages and ops-analysis topology/screen/architecture:

- Ensure outer canvas container has `min-width: 0` and `min-height: 0`.
- Ensure side panels have local scroll.
- Ensure title/label text uses `SafeText` when displayed in fixed-size nodes, cards, or sidebars.
- Ensure resize observers or existing resize handlers are preserved.

Use this class pattern:

```tsx
className="min-h-0 min-w-0 overflow-hidden"
```

- [ ] **Step 5: Verify special pages statically**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
pnpm test:ui-text-risk
```

Expected: special pages may still appear in the report, but remaining hits are justified by canvas, hero, wide table, or local scroll context.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/cmdb web/src/app/ops-analysis
git commit -m "feat: harden special ui surfaces"
```

### Task 11: Final Verification And Review Package

**Files:**
- Modify: `docs/superpowers/specs/2026-07-15-ui-interaction-unification-design.md`
- Modify: `docs/superpowers/plans/2026-07-15-ui-interaction-unification.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified implementation summary and residual risk list.

- [x] **Step 1: Run full three-app checks**

Run:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
pnpm test:ui-i18n-keys
pnpm test:ui-shell-components
pnpm test:ui-text-risk
NEXTAPI_INSTALL_APP=ops-analysis,alarm,cmdb pnpm type-check
```

Expected:

- `test:ui-i18n-keys`: PASS.
- `test:ui-shell-components`: PASS.
- `test:ui-text-risk`: prints ranked risks.
- `type-check`: PASS.

Actual:

- `pnpm test:ui-i18n-keys`: PASS.
- `pnpm test:ui-shell-components`: PASS.
- `pnpm test:ui-text-risk`: PASS/report; remaining ranked risks are documented as special-page or historical-risk residuals.
- `NEXTAPI_INSTALL_APP=ops-analysis,alarm,cmdb pnpm type-check`: PASS.
- Additional `pnpm lint`: blocked by unrelated baseline lint errors in storybook/monitor/log/opspilot/CMDB changeRecords; no errors from this task's touched files appeared in the full lint output.

- [x] **Step 2: Run page smoke checks manually**

Start dev server:

```bash
cd /Users/hong/Desktop/weops相关/new-weops-x/bk-lite.worktrees/codex-ui-interaction-unification/web
NEXTAPI_INSTALL_APP=ops-analysis,alarm,cmdb pnpm dev
```

Open these pages in Chinese and English at 1440, 1280, 1024 width and 720 height:

- `/ops-analysis/settings/dataSource`
- `/ops-analysis/settings/namespace`
- `/ops-analysis/view`
- `/alarm/alarms`
- `/alarm/incidents`
- `/alarm/settings/actionRules`
- `/alarm/settings/correlationRules`
- `/alarm/integration`
- `/cmdb/assetSearch`
- `/cmdb/assetData`
- `/cmdb/assetManage/management`
- `/cmdb/assetManage/operationLog`

Expected:

- no whole-page unintended horizontal scroll,
- toolbar wraps or folds,
- table footer and pagination visible,
- Modal/Drawer footer visible,
- long text accessible by Tooltip,
- risk/empty/error messages visible outside Tooltip.

Actual:

- Started dev server with Node 24 on port 3002 because port 3000 was already in use and system `node` was v18.
- Initial browser smoke was blocked by missing `@tailwindcss/oxide-darwin-arm64`; running `pnpm install` with Node 24 restored the optional native package without changing lockfile.
- Playwright smoke then confirmed the sampled routes compile and return 200.
- Full business-page visual verification is limited by unauthenticated local state and missing `NEXTAPI_URL`: most routes redirect to `/auth/signin`, and login-related proxy calls return 500 from `undefined/api/...`.
- Observed 1024/760 horizontal overflow belongs to the `/auth/signin` 1280-wide shell after redirect, not to the authenticated three-module pages.

- [x] **Step 3: Update spec with residual risks**

If any page remains intentionally special, append a section to the design spec:

```markdown
## Residual Exceptions

- `<route>` keeps `<fixed/layout behavior>` because `<business reason>`. The remaining overflow is local to `<container>` and does not create whole-page horizontal scroll.
```

- [ ] **Step 4: Commit final verification notes**

```bash
git add docs/superpowers/specs/2026-07-15-ui-interaction-unification-design.md docs/superpowers/plans/2026-07-15-ui-interaction-unification.md
git commit -m "docs: record ui unification verification plan"
```

- [x] **Step 5: Prepare review summary**

Prepare final response with:

- branch and worktree path,
- commits made,
- major files changed,
- checks run and outputs,
- pages manually checked,
- residual risks.
