# Historical Superpowers change: 2026-06-30-ops-analysis-screen-mvp-interactions

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-30-ops-analysis-screen-mvp-interactions.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable BK-Lite ops-analysis Screen editor: add screen widgets, drag/resize within a fixed-resolution canvas, configure data, save/cancel, refresh, and fullscreen-preview a built-in technology-style big screen.

**Architecture:** Keep Screen as an independent fixed-resolution canvas with pixel-based layout and Screen-only visual chrome. Reuse existing Dashboard widget rendering/data configuration where possible, and inject `chartThemeMode: "screen-dark"` only through the Screen rendering path so Dashboard and Topology visuals remain unchanged. Keep MVP interactions deliberately small: no style configuration, no undo/redo, no layer panel, no template system.

**Tech Stack:** Next.js 16, React 19, TypeScript, Ant Design, existing ops-analysis widget registry/renderers, `react-rnd`, focused `tsx` scripts for pure logic tests.

---

## Scope Check

The approved spec is one subsystem: Screen MVP editing and presentation. Report, scene container, templates, rotation, multi-screen splicing, publishing, and advanced design-tool interactions stay out of this plan.

## File Structure

- Modify `web/package.json`
  Add focused `tsx` scripts for Screen layout and view-set logic tests.
- Create `web/scripts/ops-analysis-screen-layout-test.ts`
  Tests Screen item creation, movement, resize, boundary validation, deletion, and viewport changes.
- Modify `web/src/app/ops-analysis/types/screen.ts`
  Define first-class Screen item, widget type, decoration, draft, and toolbar types.
- Modify `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts`
  Normalize Screen view sets while preserving Screen theme/background/decorations.
- Create `web/src/app/ops-analysis/(pages)/view/screen/utils/layout.ts`
  Pure Screen layout operations with no React dependency.
- Create `web/src/app/ops-analysis/(pages)/view/screen/constants/widgets.ts`
  The MVP allowed widget catalog and default pixel sizes.
- Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame.tsx`
  Screen-only technology-style panel chrome.
- Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetRenderer.tsx`
  Bridges Screen items to existing widget rendering with `screen-dark` injected.
- Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetSelector.tsx`
  Simple component picker for the MVP widget catalog.
- Modify `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`
  Render fixed-ratio Screen canvas, background, decorations, view/edit modes, widget absolute layout, drag/resize bounds.
- Modify `web/src/app/ops-analysis/(pages)/view/screen/components/screenToolbar.tsx`
  Align Screen toolbar with Dashboard/Topology tool placement and edit/save/cancel behavior.
- Modify `web/src/app/ops-analysis/(pages)/view/screen/components/screenConfigModal.tsx`
  Add title/show-title/show-clock fields and block viewport save when layout would overflow.
- Modify `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`
  Own Screen loading, draft state, edit mode, selector/config modal state, refresh version, save/cancel, fullscreen preview.
- Reuse `web/src/app/ops-analysis/components/widgetConfig.tsx`
  Use existing Dashboard configuration UI for data settings. If direct reuse exposes Dashboard-only theme options, pass `showChartThemeMode={false}`.
- Modify `web/src/app/ops-analysis/locales/zh.json`
- Modify `web/src/app/ops-analysis/locales/en.json`
  Add Screen editor labels and validation messages.

## Task 1: Screen Types, Layout Utilities, And Tests

**Files:**
- Modify: `web/package.json`
- Create: `web/scripts/ops-analysis-screen-layout-test.ts`
- Modify: `web/src/app/ops-analysis/types/screen.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/utils/layout.ts`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/constants/widgets.ts`

- [ ] **Step 1: Add the failing test script**

Modify `web/package.json` scripts:

```json
"test:ops-analysis-screen-layout": "pnpm exec tsx scripts/ops-analysis-screen-layout-test.ts"
```

Keep existing scripts unchanged.

- [ ] **Step 2: Create the failing layout test**

Create `web/scripts/ops-analysis-screen-layout-test.ts`:

```ts
import assert from 'node:assert/strict';

import { SCREEN_WIDGET_DEFINITIONS } from '../src/app/ops-analysis/(pages)/view/screen/constants/widgets';
import {
  addScreenWidget,
  canViewportContainItems,
  deleteScreenItem,
  isScreenItemInsideViewport,
  moveScreenItem,
  resizeScreenItem,
  sanitizeScreenItems,
} from '../src/app/ops-analysis/(pages)/view/screen/utils/layout';
import { buildDefaultScreenViewSets } from '../src/app/ops-analysis/(pages)/view/screen/utils/viewport';
import type { ScreenViewSets } from '../src/app/ops-analysis/types/screen';

assert.deepEqual(
  SCREEN_WIDGET_DEFINITIONS.map((item) => item.chartType),
  ['single', 'gauge', 'line', 'bar', 'pie', 'topN', 'eventTable', 'networkStatusTopology'],
);

const base = buildDefaultScreenViewSets();
const withSingle = addScreenWidget(base, 'single');
assert.equal(withSingle.items.length, 1);
assert.equal(withSingle.items[0].chartType, 'single');
assert.equal(withSingle.items[0].x, 48);
assert.equal(withSingle.items[0].y, 96);
assert.equal(withSingle.items[0].w, 300);
assert.equal(withSingle.items[0].h, 150);
assert.equal(withSingle.items[0].config.chartThemeMode, 'screen-dark');

const moved = moveScreenItem(withSingle, withSingle.items[0].id, { x: 2000, y: -40 });
assert.equal(moved.items[0].x, 1620);
assert.equal(moved.items[0].y, 0);

const resized = resizeScreenItem(withSingle, withSingle.items[0].id, { w: 5000, h: 5000 });
assert.equal(resized.items[0].w, 1872);
assert.equal(resized.items[0].h, 984);

assert.equal(isScreenItemInsideViewport(withSingle.items[0], withSingle.viewport), true);
assert.equal(
  isScreenItemInsideViewport(
    { ...withSingle.items[0], x: 1900, w: 200 },
    withSingle.viewport,
  ),
  false,
);

const unsafe: ScreenViewSets = {
  ...withSingle,
  items: [
    withSingle.items[0],
    { ...withSingle.items[0], id: withSingle.items[0].id, x: -1 },
    { ...withSingle.items[0], id: 'bad-size', w: 0 },
  ],
};
assert.deepEqual(
  sanitizeScreenItems(unsafe.items, unsafe.viewport).map((item) => item.id),
  [withSingle.items[0].id],
);

assert.equal(canViewportContainItems(withSingle.items, { width: 200, height: 200 }), false);
assert.equal(canViewportContainItems(withSingle.items, { width: 1920, height: 1080 }), true);

const deleted = deleteScreenItem(withSingle, withSingle.items[0].id);
assert.equal(deleted.items.length, 0);

const twoWidgets = addScreenWidget(withSingle, 'line');
assert.notEqual(twoWidgets.items[0].id, twoWidgets.items[1].id);
assert.equal(twoWidgets.items[1].zIndex, twoWidgets.items[0].zIndex + 1);

console.log('ops-analysis screen layout tests passed');
```

- [ ] **Step 3: Run the test and confirm it fails**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-layout
```

Expected: FAIL with a module resolution error for `screen/constants/widgets` or `screen/utils/layout`.

- [ ] **Step 4: Replace Screen types with the MVP contract**

Modify `web/src/app/ops-analysis/types/screen.ts`:

```ts
import type { DirItem } from './index';
import type { ValueConfig } from './dashBoard';

export type ScreenWidgetChartType =
  | 'single'
  | 'gauge'
  | 'line'
  | 'bar'
  | 'pie'
  | 'topN'
  | 'eventTable'
  | 'networkStatusTopology';

export interface ScreenViewportConfig {
  width: number;
  height: number;
  background?: {
    type?: string;
    key?: string;
  };
  theme?: 'screen-tech-blue';
}

export interface ScreenDecorationsConfig {
  showTitle?: boolean;
  showClock?: boolean;
  title?: string;
}

export interface ScreenWidgetItem {
  id: string;
  type: 'widget';
  chartType: ScreenWidgetChartType;
  title: string;
  x: number;
  y: number;
  w: number;
  h: number;
  zIndex: number;
  config: ValueConfig;
}

export type ScreenItem = ScreenWidgetItem;

export interface ScreenViewSets {
  viewport: ScreenViewportConfig;
  items: ScreenItem[];
  decorations: ScreenDecorationsConfig;
}

export interface ScreenProps {
  selectedScreen?: DirItem | null;
}
```

- [ ] **Step 5: Add the MVP widget catalog**

Create `web/src/app/ops-analysis/(pages)/view/screen/constants/widgets.ts`:

```ts
import type { ScreenWidgetChartType } from '@/app/ops-analysis/types/screen';

export interface ScreenWidgetDefinition {
  chartType: ScreenWidgetChartType;
  titleKey: string;
  descriptionKey: string;
  defaultWidth: number;
  defaultHeight: number;
}

export const SCREEN_WIDGET_DEFINITIONS: ScreenWidgetDefinition[] = [
  {
    chartType: 'single',
    titleKey: 'opsAnalysis.screen.widgets.single',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.single',
    defaultWidth: 300,
    defaultHeight: 150,
  },
  {
    chartType: 'gauge',
    titleKey: 'opsAnalysis.screen.widgets.gauge',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.gauge',
    defaultWidth: 340,
    defaultHeight: 240,
  },
  {
    chartType: 'line',
    titleKey: 'opsAnalysis.screen.widgets.line',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.line',
    defaultWidth: 520,
    defaultHeight: 300,
  },
  {
    chartType: 'bar',
    titleKey: 'opsAnalysis.screen.widgets.bar',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.bar',
    defaultWidth: 520,
    defaultHeight: 300,
  },
  {
    chartType: 'pie',
    titleKey: 'opsAnalysis.screen.widgets.pie',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.pie',
    defaultWidth: 360,
    defaultHeight: 300,
  },
  {
    chartType: 'topN',
    titleKey: 'opsAnalysis.screen.widgets.topN',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.topN',
    defaultWidth: 420,
    defaultHeight: 320,
  },
  {
    chartType: 'eventTable',
    titleKey: 'opsAnalysis.screen.widgets.eventTable',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.eventTable',
    defaultWidth: 520,
    defaultHeight: 360,
  },
  {
    chartType: 'networkStatusTopology',
    titleKey: 'opsAnalysis.screen.widgets.networkStatusTopology',
    descriptionKey: 'opsAnalysis.screen.widgetDescriptions.networkStatusTopology',
    defaultWidth: 620,
    defaultHeight: 420,
  },
];

export const getScreenWidgetDefinition = (chartType: ScreenWidgetChartType) =>
  SCREEN_WIDGET_DEFINITIONS.find((item) => item.chartType === chartType);
```

- [ ] **Step 6: Update viewport normalization**

Modify `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts` so the default view sets include the built-in theme, background, and decorations:

```ts
import type {
  ScreenDecorationsConfig,
  ScreenViewportConfig,
  ScreenViewSets,
} from '@/app/ops-analysis/types/screen';

export interface ScreenViewportPreset {
  key: string;
  label: string;
  width: number;
  height: number;
}

export const DEFAULT_SCREEN_VIEWPORT: ScreenViewportConfig = {
  width: 1920,
  height: 1080,
  background: { type: 'builtIn', key: 'tech-grid' },
  theme: 'screen-tech-blue',
};

export const DEFAULT_SCREEN_DECORATIONS: ScreenDecorationsConfig = {
  showTitle: true,
  showClock: true,
  title: '',
};

export const SCREEN_VIEWPORT_PRESETS: ScreenViewportPreset[] = [
  { key: '1920x1080', label: '1920 × 1080', width: 1920, height: 1080 },
  { key: '1366x768', label: '1366 × 768', width: 1366, height: 768 },
  { key: '3840x2160', label: '3840 × 2160', width: 3840, height: 2160 },
];

export const isValidViewportSize = (value: unknown): value is number =>
  typeof value === 'number' &&
  Number.isInteger(value) &&
  Number.isFinite(value) &&
  value > 0;

const cloneViewport = (viewport: ScreenViewportConfig): ScreenViewportConfig => ({
  ...viewport,
  background: viewport.background ? { ...viewport.background } : undefined,
});

export const buildDefaultScreenViewSets = (): ScreenViewSets => ({
  viewport: cloneViewport(DEFAULT_SCREEN_VIEWPORT),
  items: [],
  decorations: { ...DEFAULT_SCREEN_DECORATIONS },
});

export const normalizeScreenViewSets = (value: unknown): ScreenViewSets => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return buildDefaultScreenViewSets();
  }

  const source = value as Partial<ScreenViewSets>;
  const viewport =
    source.viewport && typeof source.viewport === 'object' && !Array.isArray(source.viewport)
      ? source.viewport
      : {};
  const decorations =
    source.decorations &&
    typeof source.decorations === 'object' &&
    !Array.isArray(source.decorations)
      ? source.decorations
      : {};

  return {
    viewport: {
      width: isValidViewportSize(viewport.width)
        ? viewport.width
        : DEFAULT_SCREEN_VIEWPORT.width,
      height: isValidViewportSize(viewport.height)
        ? viewport.height
        : DEFAULT_SCREEN_VIEWPORT.height,
      background: DEFAULT_SCREEN_VIEWPORT.background
        ? { ...DEFAULT_SCREEN_VIEWPORT.background }
        : undefined,
      theme: DEFAULT_SCREEN_VIEWPORT.theme,
    },
    items: Array.isArray(source.items) ? source.items : [],
    decorations: {
      ...DEFAULT_SCREEN_DECORATIONS,
      ...decorations,
    },
  };
};

export const updateScreenViewport = (
  viewSets: ScreenViewSets,
  viewport: ScreenViewportConfig,
): ScreenViewSets => ({
  ...viewSets,
  viewport: {
    ...viewSets.viewport,
    width: viewport.width,
    height: viewport.height,
  },
  items: [...viewSets.items],
  decorations: { ...viewSets.decorations },
});
```

- [ ] **Step 7: Add pure layout utilities**

Create `web/src/app/ops-analysis/(pages)/view/screen/utils/layout.ts`:

```ts
import { v4 as uuidv4 } from 'uuid';
import type {
  ScreenItem,
  ScreenViewSets,
  ScreenViewportConfig,
  ScreenWidgetChartType,
  ScreenWidgetItem,
} from '@/app/ops-analysis/types/screen';
import { getScreenWidgetDefinition } from '../constants/widgets';

const DEFAULT_INSERT_X = 48;
const DEFAULT_INSERT_Y = 96;

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

const getNextZIndex = (items: ScreenItem[]) =>
  items.reduce((max, item) => Math.max(max, item.zIndex || 0), 0) + 1;

export const isScreenItemInsideViewport = (
  item: ScreenItem,
  viewport: ScreenViewportConfig,
) =>
  Number.isFinite(item.x) &&
  Number.isFinite(item.y) &&
  Number.isFinite(item.w) &&
  Number.isFinite(item.h) &&
  item.x >= 0 &&
  item.y >= 0 &&
  item.w > 0 &&
  item.h > 0 &&
  item.x + item.w <= viewport.width &&
  item.y + item.h <= viewport.height;

export const sanitizeScreenItems = (
  items: ScreenItem[],
  viewport: ScreenViewportConfig,
) => {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (!item.id || seen.has(item.id)) return false;
    if (!isScreenItemInsideViewport(item, viewport)) return false;
    seen.add(item.id);
    return true;
  });
};

export const canViewportContainItems = (
  items: ScreenItem[],
  viewport: ScreenViewportConfig,
) => items.every((item) => isScreenItemInsideViewport(item, viewport));

export const createScreenWidgetItem = (
  chartType: ScreenWidgetChartType,
  existingItems: ScreenItem[],
): ScreenWidgetItem => {
  const definition = getScreenWidgetDefinition(chartType);
  if (!definition) {
    throw new Error(`Unsupported screen widget type: ${chartType}`);
  }

  return {
    id: uuidv4(),
    type: 'widget',
    chartType,
    title: '',
    x: DEFAULT_INSERT_X,
    y: DEFAULT_INSERT_Y,
    w: definition.defaultWidth,
    h: definition.defaultHeight,
    zIndex: getNextZIndex(existingItems),
    config: {
      chartType,
      chartThemeMode: 'screen-dark',
      ...(chartType === 'networkStatusTopology'
        ? {
          sceneWidgetType: 'networkStatusTopology',
        }
        : {}),
    },
  };
};

export const addScreenWidget = (
  viewSets: ScreenViewSets,
  chartType: ScreenWidgetChartType,
): ScreenViewSets => ({
  ...viewSets,
  items: [...viewSets.items, createScreenWidgetItem(chartType, viewSets.items)],
});

export const moveScreenItem = (
  viewSets: ScreenViewSets,
  itemId: string,
  position: { x: number; y: number },
): ScreenViewSets => ({
  ...viewSets,
  items: viewSets.items.map((item) =>
    item.id === itemId
      ? {
        ...item,
        x: clamp(position.x, 0, viewSets.viewport.width - item.w),
        y: clamp(position.y, 0, viewSets.viewport.height - item.h),
      }
      : item,
  ),
});

export const resizeScreenItem = (
  viewSets: ScreenViewSets,
  itemId: string,
  size: { w: number; h: number },
): ScreenViewSets => ({
  ...viewSets,
  items: viewSets.items.map((item) =>
    item.id === itemId
      ? {
        ...item,
        w: clamp(size.w, 1, viewSets.viewport.width - item.x),
        h: clamp(size.h, 1, viewSets.viewport.height - item.y),
      }
      : item,
  ),
});

export const updateScreenItemConfig = (
  viewSets: ScreenViewSets,
  itemId: string,
  nextItem: ScreenItem,
): ScreenViewSets => ({
  ...viewSets,
  items: viewSets.items.map((item) => (item.id === itemId ? nextItem : item)),
});

export const deleteScreenItem = (
  viewSets: ScreenViewSets,
  itemId: string,
): ScreenViewSets => ({
  ...viewSets,
  items: viewSets.items.filter((item) => item.id !== itemId),
});
```

- [ ] **Step 8: Run tests and fix type errors**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-layout
```

Expected: PASS and prints `ops-analysis screen layout tests passed`.

- [ ] **Step 9: Commit Task 1**

```bash
git add web/package.json web/scripts/ops-analysis-screen-layout-test.ts web/src/app/ops-analysis/types/screen.ts 'web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts' 'web/src/app/ops-analysis/(pages)/view/screen/utils/layout.ts' 'web/src/app/ops-analysis/(pages)/view/screen/constants/widgets.ts'
git commit -m "feat(ops-analysis): add screen layout primitives"
```

## Task 2: Screen Widget Frame And Private Technology Styling

**Files:**
- Create: `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`

- [ ] **Step 1: Use frontend design guidance before coding the visual shell**

Read `/Users/hong/.agents/skills/frontend-design/SKILL.md` and use it for this task. The visual direction is: industrial technology wall-screen, dark blue-black canvas, cyan telemetry accents, restrained glow, dense but legible operations display. Do not use this styling outside Screen.

- [ ] **Step 2: Create ScreenWidgetFrame**

Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame.tsx`:

```tsx
'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';

interface ScreenWidgetFrameProps {
  item: ScreenWidgetItem;
  selected?: boolean;
  editMode?: boolean;
  onConfigure?: () => void;
  onDelete?: () => void;
  children: React.ReactNode;
}

const emphasisClassByType: Record<string, string> = {
  single: 'screen-widget-frame--kpi',
  gauge: 'screen-widget-frame--gauge',
  topN: 'screen-widget-frame--rank',
  eventTable: 'screen-widget-frame--event',
  networkStatusTopology: 'screen-widget-frame--topology',
};

const ScreenWidgetFrame: React.FC<ScreenWidgetFrameProps> = ({
  item,
  selected = false,
  editMode = false,
  onConfigure,
  onDelete,
  children,
}) => {
  const { t } = useTranslation();
  const emphasisClass = emphasisClassByType[item.chartType] || 'screen-widget-frame--chart';

  return (
    <section
      className={[
        'screen-widget-frame',
        emphasisClass,
        selected ? 'screen-widget-frame--selected' : '',
        editMode ? 'screen-widget-frame--editable' : '',
      ].filter(Boolean).join(' ')}
    >
      <div className="screen-widget-frame__corners" aria-hidden="true" />
      <header className="screen-widget-frame__header">
        <span className="screen-widget-frame__title">
          {item.title || item.config?.name || item.chartType}
        </span>
        <span className="screen-widget-frame__signal" aria-hidden="true" />
      </header>
      {editMode && selected && (
        <div className="screen-widget-frame__actions">
          <button
            type="button"
            className="screen-widget-frame__action"
            onClick={(event) => {
              event.stopPropagation();
              onConfigure?.();
            }}
          >
            {t('opsAnalysis.screen.editWidget')}
          </button>
          <button
            type="button"
            className="screen-widget-frame__action screen-widget-frame__action--danger"
            onClick={(event) => {
              event.stopPropagation();
              onDelete?.();
            }}
          >
            {t('opsAnalysis.screen.deleteWidget')}
          </button>
        </div>
      )}
      <div className="screen-widget-frame__body">{children}</div>
    </section>
  );
};

export default ScreenWidgetFrame;
```

- [ ] **Step 3: Add Screen-only CSS through ScreenCanvas**

Modify `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx` by adding the style block below inside the returned root element. Keep it local to ScreenCanvas so it does not affect Dashboard or Topology:

```tsx
<style jsx global>{`
  .screen-tech-canvas {
    color: #eafbff;
    background:
      linear-gradient(rgba(74, 222, 255, 0.045) 1px, transparent 1px),
      linear-gradient(90deg, rgba(74, 222, 255, 0.045) 1px, transparent 1px),
      radial-gradient(circle at 50% 12%, rgba(56, 189, 248, 0.24), transparent 34%),
      radial-gradient(circle at 14% 24%, rgba(59, 130, 246, 0.16), transparent 28%),
      linear-gradient(135deg, #020918 0%, #06233d 54%, #020611 100%);
    background-size: 48px 48px, 48px 48px, auto, auto, auto;
  }

  .screen-widget-frame {
    position: relative;
    display: flex;
    height: 100%;
    min-height: 0;
    flex-direction: column;
    overflow: hidden;
    border: 1px solid rgba(109, 226, 255, 0.32);
    background:
      linear-gradient(180deg, rgba(8, 34, 56, 0.64), rgba(3, 14, 30, 0.46)),
      rgba(4, 18, 36, 0.54);
    box-shadow:
      0 18px 44px rgba(0, 10, 28, 0.34),
      inset 0 1px 0 rgba(226, 251, 255, 0.12),
      inset 0 -26px 48px rgba(14, 116, 144, 0.08);
    backdrop-filter: blur(16px) saturate(128%);
  }

  .screen-widget-frame::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background:
      linear-gradient(90deg, rgba(54, 231, 255, 0.18), transparent 18%, transparent 82%, rgba(54, 231, 255, 0.14)),
      linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 38%);
    opacity: 0.72;
  }

  .screen-widget-frame--selected {
    border-color: rgba(125, 235, 255, 0.78);
    box-shadow:
      0 0 0 1px rgba(125, 235, 255, 0.26),
      0 0 22px rgba(54, 231, 255, 0.3),
      inset 0 1px 0 rgba(226, 251, 255, 0.16);
  }

  .screen-widget-frame__corners::before,
  .screen-widget-frame__corners::after {
    content: "";
    position: absolute;
    z-index: 2;
    width: 20px;
    height: 20px;
    pointer-events: none;
    border-color: rgba(125, 235, 255, 0.72);
  }

  .screen-widget-frame__corners::before {
    left: 7px;
    top: 7px;
    border-left: 2px solid;
    border-top: 2px solid;
  }

  .screen-widget-frame__corners::after {
    right: 7px;
    bottom: 7px;
    border-right: 2px solid;
    border-bottom: 2px solid;
  }

  .screen-widget-frame__header {
    position: relative;
    z-index: 1;
    display: flex;
    height: 34px;
    flex-shrink: 0;
    align-items: center;
    justify-content: space-between;
    padding: 0 14px;
    border-bottom: 1px solid rgba(109, 226, 255, 0.16);
    background: linear-gradient(90deg, rgba(54, 231, 255, 0.14), transparent 68%);
  }

  .screen-widget-frame__title {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #eafbff;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0;
  }

  .screen-widget-frame__signal {
    width: 36px;
    height: 2px;
    flex-shrink: 0;
    background: linear-gradient(90deg, transparent, #6ef4ff);
    box-shadow: 0 0 12px rgba(54, 231, 255, 0.55);
  }

  .screen-widget-frame__body {
    position: relative;
    z-index: 1;
    min-height: 0;
    flex: 1;
    padding: 10px;
  }

  .screen-widget-frame__actions {
    position: absolute;
    right: 10px;
    top: 42px;
    z-index: 4;
    display: flex;
    gap: 6px;
  }

  .screen-widget-frame__action {
    height: 24px;
    border: 1px solid rgba(125, 235, 255, 0.48);
    background: rgba(4, 18, 36, 0.88);
    color: #dffbff;
    padding: 0 8px;
    font-size: 12px;
    cursor: pointer;
  }

  .screen-widget-frame__action--danger {
    border-color: rgba(248, 113, 113, 0.62);
    color: #fecaca;
  }
`}</style>
```

- [ ] **Step 4: Run lint on touched files**

Run:

```bash
cd web && pnpm lint -- --file 'src/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame.tsx' --file 'src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx'
```

Expected: PASS. If the local lint command does not support `--file`, run `cd web && pnpm lint` and confirm no Screen-related errors.

- [ ] **Step 5: Commit Task 2**

```bash
git add 'web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetFrame.tsx' 'web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx'
git commit -m "feat(ops-analysis): add screen technology widget frame"
```

## Task 3: Screen Widget Rendering Bridge

**Files:**
- Create: `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetRenderer.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetDataRenderer.tsx`

- [ ] **Step 1: Export the existing WidgetWrapper props**

Modify `web/src/app/ops-analysis/components/widgetDataRenderer.tsx` by changing the existing local props interface to an exported interface. Do not change the component body.

```ts
export interface WidgetWrapperProps {
  dashboardId?: number | string;
  widgetId: string;
  chartType?: string;
  config?: ValueConfig;
  onReady?: (hasData?: boolean) => void;
  dataSource?: DatasourceItem;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterDefinitions?: UnifiedFilterDefinition[];
  filterSearchVersion?: number;
  namespaceSearchVersion?: number;
  reloadVersion?: string;
  builtinNamespaceId?: number;
}
```

- [ ] **Step 2: Create ScreenWidgetRenderer**

Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetRenderer.tsx`:

```tsx
'use client';

import React, { useMemo } from 'react';
import WidgetWrapper from '@/app/ops-analysis/components/widgetDataRenderer';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import ScreenWidgetFrame from './screenWidgetFrame';

interface ScreenWidgetRendererProps {
  item: ScreenWidgetItem;
  selected?: boolean;
  editMode?: boolean;
  refreshVersion: number;
  screenId?: string | number;
  dataSourceResolver: (dataSource?: string | number) => DatasourceItem | undefined;
  onEditConfig?: (item: ScreenWidgetItem) => void;
  onDelete?: (itemId: string) => void;
}

const EMPTY_FILTER_VALUES: Record<string, FilterValue> = {};
const EMPTY_FILTER_DEFINITIONS: UnifiedFilterDefinition[] = [];

const ScreenWidgetRenderer: React.FC<ScreenWidgetRendererProps> = ({
  item,
  selected = false,
  editMode = false,
  refreshVersion,
  screenId,
  dataSourceResolver,
  onEditConfig,
  onDelete,
}) => {
  const widgetConfig = useMemo(
    () => ({
      ...item.config,
      name: item.title || item.config?.name || item.chartType,
      chartType: item.chartType,
      chartThemeMode: 'screen-dark' as const,
      ...(item.chartType === 'networkStatusTopology'
        ? { sceneWidgetType: 'networkStatusTopology' as const }
        : {}),
    }),
    [item],
  );
  const dataSource = dataSourceResolver(widgetConfig.dataSource);

  return (
    <ScreenWidgetFrame
      item={item}
      selected={selected}
      editMode={editMode}
      onConfigure={() => onEditConfig?.(item)}
      onDelete={() => onDelete?.(item.id)}
    >
      <WidgetWrapper
        dashboardId={screenId}
        widgetId={item.id}
        chartType={item.chartType}
        config={widgetConfig}
        dataSource={dataSource}
        filterSearchVersion={0}
        namespaceSearchVersion={0}
        reloadVersion={`screen:${refreshVersion}`}
        unifiedFilterValues={EMPTY_FILTER_VALUES}
        filterDefinitions={EMPTY_FILTER_DEFINITIONS}
      />
    </ScreenWidgetFrame>
  );
};

export default ScreenWidgetRenderer;
```

- [ ] **Step 3: Run type check for the bridge**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS with `WidgetWrapperProps` exported and no Dashboard behavior changes.

- [ ] **Step 4: Commit Task 3**

```bash
git add 'web/src/app/ops-analysis/components/widgetDataRenderer.tsx' 'web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetRenderer.tsx'
git commit -m "feat(ops-analysis): render dashboard widgets in screen"
```

## Task 4: Screen Canvas Edit, Drag, Resize, And Boundaries

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`

- [ ] **Step 1: Extend ScreenCanvas props**

Modify the props in `screenCanvas.tsx`:

```ts
interface ScreenCanvasProps {
  viewSets: ScreenViewSets;
  fullscreen?: boolean;
  editMode?: boolean;
  selectedItemId?: string | null;
  refreshVersion?: number;
  dataSourceResolver?: (dataSource?: string | number) => DatasourceItem | undefined;
  onSelectItem?: (itemId: string | null) => void;
  onMoveItem?: (itemId: string, position: { x: number; y: number }) => void;
  onResizeItem?: (itemId: string, size: { w: number; h: number }) => void;
  onEditItem?: (itemId: string) => void;
  onDeleteItem?: (itemId: string) => void;
}
```

Add imports:

```ts
import { Rnd } from 'react-rnd';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import ScreenWidgetRenderer from './screenWidgetRenderer';
```

- [ ] **Step 2: Add pixel scale helpers**

Inside `ScreenCanvas`, compute the design-to-render scale:

```ts
const scale = canvasSize ? canvasSize.width / width : 1;
const toRendered = (value: number) => value * scale;
const toDesign = (value: number) => Math.round(value / scale);
```

- [ ] **Step 3: Render canvas with Screen background and decorations**

Replace the current empty-canvas body with:

```tsx
<div
  className="screen-tech-canvas relative h-full w-full overflow-hidden"
  onClick={() => editMode && onSelectItem?.(null)}
>
  {viewSets.decorations.showTitle && (
    <div className="pointer-events-none absolute left-0 right-0 top-5 z-20 text-center">
      <div className="inline-flex items-center justify-center px-10 py-2 text-2xl font-bold text-cyan-50">
        {viewSets.decorations.title || t('opsAnalysis.screen.defaultTitle')}
      </div>
    </div>
  )}
  {viewSets.decorations.showClock && (
    <div className="pointer-events-none absolute right-8 top-6 z-20 text-sm font-medium text-cyan-100/80">
      {new Date().toLocaleTimeString()}
    </div>
  )}
  {viewSets.items.length === 0 ? (
    <div className="flex h-full w-full items-center justify-center p-8">
      <Empty
        description={
          <span className="text-cyan-100/70">
            {t('opsAnalysis.screen.canvasEmpty')}
          </span>
        }
      />
    </div>
  ) : (
    viewSets.items.map((item) => renderScreenItem(item))
  )}
</div>
```

- [ ] **Step 4: Add item rendering with edit-mode absolute layout**

Add this helper inside `ScreenCanvas`:

```tsx
const renderScreenItem = (item: ScreenWidgetItem) => {
  const selected = selectedItemId === item.id;
  const left = toRendered(item.x);
  const top = toRendered(item.y);
  const renderedWidth = toRendered(item.w);
  const renderedHeight = toRendered(item.h);

  const content = (
    <ScreenWidgetRenderer
      item={item}
      selected={selected}
      editMode={editMode}
      refreshVersion={refreshVersion}
      dataSourceResolver={dataSourceResolver || (() => undefined)}
      onEditConfig={() => onEditItem?.(item.id)}
      onDelete={onDeleteItem}
    />
  );

  if (!editMode || fullscreen) {
    return (
      <div
        key={item.id}
        style={{
          position: 'absolute',
          left,
          top,
          width: renderedWidth,
          height: renderedHeight,
          zIndex: item.zIndex,
        }}
      >
        {content}
      </div>
    );
  }

  return (
    <ResizableBox
      key={item.id}
      width={renderedWidth}
      height={renderedHeight}
      minConstraints={[toRendered(80), toRendered(64)]}
      maxConstraints={[
        toRendered(width - item.x),
        toRendered(height - item.y),
      ]}
      resizeHandles={['se']}
      onResizeStop={(_, data) => {
        onResizeItem?.(item.id, {
          w: toDesign(data.size.width),
          h: toDesign(data.size.height),
        });
      }}
      style={{
        position: 'absolute',
        left,
        top,
        zIndex: item.zIndex,
      }}
    >
      <div
        className="h-full w-full cursor-move"
        draggable
        onClick={(event) => {
          event.stopPropagation();
          onSelectItem?.(item.id);
        }}
        onDoubleClick={(event) => {
          event.stopPropagation();
          onEditItem?.(item.id);
        }}
        onDragEnd={(event) => {
          const parent = (event.currentTarget.closest('.screen-tech-canvas') as HTMLElement | null);
          if (!parent) return;
          const rect = parent.getBoundingClientRect();
          onMoveItem?.(item.id, {
            x: toDesign(event.clientX - rect.left - renderedWidth / 2),
            y: toDesign(event.clientY - rect.top - renderedHeight / 2),
          });
        }}
      >
        {content}
      </div>
    </ResizableBox>
  );
};
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-layout
cd web && pnpm type-check
```

Expected: both PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add 'web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx'
git commit -m "feat(ops-analysis): support screen widget layout editing"
```

## Task 5: Selector, Toolbar, Settings, And Locale Copy

**Files:**
- Create: `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetSelector.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenToolbar.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenConfigModal.tsx`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`

- [ ] **Step 1: Create the Screen widget selector**

Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetSelector.tsx`:

```tsx
'use client';

import React from 'react';
import { Button, List, Modal } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import type { ScreenWidgetChartType } from '@/app/ops-analysis/types/screen';
import { SCREEN_WIDGET_DEFINITIONS } from '../constants/widgets';

interface ScreenWidgetSelectorProps {
  open: boolean;
  onCancel: () => void;
  onAdd: (chartType: ScreenWidgetChartType) => void;
}

const ScreenWidgetSelector: React.FC<ScreenWidgetSelectorProps> = ({
  open,
  onCancel,
  onAdd,
}) => {
  const { t } = useTranslation();

  return (
    <Modal
      title={t('opsAnalysis.screen.addWidget')}
      open={open}
      width={720}
      footer={null}
      onCancel={onCancel}
      destroyOnHidden
    >
      <List
        grid={{ gutter: 12, column: 2 }}
        dataSource={SCREEN_WIDGET_DEFINITIONS}
        renderItem={(item) => (
          <List.Item>
            <button
              type="button"
              className="flex min-h-24 w-full flex-col rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-4 text-left transition hover:border-cyan-400 hover:shadow-[0_10px_24px_rgba(14,165,233,0.16)]"
              onClick={() => onAdd(item.chartType)}
            >
              <span className="text-sm font-semibold text-[var(--color-text-1)]">
                {t(item.titleKey)}
              </span>
              <span className="mt-1 text-xs leading-5 text-[var(--color-text-3)]">
                {t(item.descriptionKey)}
              </span>
              <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-cyan-600">
                <PlusOutlined />
                {t('opsAnalysis.screen.addThisWidget')}
              </span>
            </button>
          </List.Item>
        )}
      />
    </Modal>
  );
};

export default ScreenWidgetSelector;
```

- [ ] **Step 2: Expand ScreenToolbar props and UI**

Modify `screenToolbar.tsx` props:

```ts
interface ScreenToolbarProps {
  selectedScreen?: DirItem | null;
  editMode: boolean;
  saving?: boolean;
  onRefresh: () => void;
  onOpenSettings: () => void;
  onOpenWidgetSelector: () => void;
  onPreview: () => void;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
}
```

Use this button order:

```tsx
<Tooltip title={t('common.refresh')}>
  <Button type="text" icon={<ReloadOutlined />} className={iconButtonClassName} onClick={onRefresh} />
</Tooltip>
<Tooltip title={t('opsAnalysis.screen.fullscreenPreview')}>
  <Button type="text" icon={<FullscreenOutlined />} className={iconButtonClassName} onClick={onPreview} />
</Tooltip>
<Tooltip title={t('opsAnalysis.screen.canvasSettings')}>
  <Button type="text" icon={<SettingOutlined />} loading={saving} className={iconButtonClassName} onClick={onOpenSettings} />
</Tooltip>
{editMode && (
  <Button type="default" icon={<PlusOutlined />} className="rounded-full!" onClick={onOpenWidgetSelector}>
    {t('opsAnalysis.screen.addWidget')}
  </Button>
)}
{!editMode ? (
  <PermissionWrapper requiredPermissions={['EditChart']}>
    <Tooltip title={t('common.edit')}>
      <Button
        type="text"
        icon={<EditOutlined />}
        disabled={!selectedScreen?.data_id || selectedScreen?.is_build_in}
        className={iconButtonClassName}
        onClick={onEdit}
      />
    </Tooltip>
  </PermissionWrapper>
) : (
  <PermissionWrapper requiredPermissions={['EditChart']}>
    <div className="ml-2 flex items-center gap-2">
      <Button className="rounded-full!" onClick={onCancel}>{t('common.cancel')}</Button>
      <Button type="primary" loading={saving} className="rounded-full!" onClick={onSave}>{t('common.save')}</Button>
    </div>
  </PermissionWrapper>
)}
```

Add imports for `DirItem`, `PermissionWrapper`, and icons:

```ts
import {
  EditOutlined,
  FullscreenOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import type { DirItem } from '@/app/ops-analysis/types';
```

- [ ] **Step 3: Add title and decoration fields to ScreenConfigModal**

Extend form values in `screenConfigModal.tsx`:

```ts
interface ScreenConfigFormValues {
  preset: string;
  width: number;
  height: number;
  title: string;
  showTitle: boolean;
  showClock: boolean;
}
```

Extend props:

```ts
decorations: ScreenDecorationsConfig;
onSave: (payload: {
  viewport: ScreenViewportConfig;
  decorations: ScreenDecorationsConfig;
}) => void;
canSaveViewport?: (viewport: ScreenViewportConfig) => boolean;
```

Set fields on open:

```ts
form.setFieldsValue({
  preset: getPresetKey(viewport),
  width: viewport.width,
  height: viewport.height,
  title: decorations.title || '',
  showTitle: decorations.showTitle !== false,
  showClock: decorations.showClock !== false,
});
```

In `handleOk`, block overflow:

```ts
const values = await form.validateFields();
const nextViewport = { width: values.width, height: values.height };
if (canSaveViewport && !canSaveViewport(nextViewport)) {
  message.error(t('opsAnalysis.screen.viewportContainsOverflow'));
  return;
}
onSave({
  viewport: nextViewport,
  decorations: {
    title: values.title,
    showTitle: values.showTitle,
    showClock: values.showClock,
  },
});
```

Add form items:

```tsx
<Form.Item name="title" label={t('opsAnalysis.screen.screenTitle')}>
  <Input maxLength={64} placeholder={t('opsAnalysis.screen.defaultTitle')} />
</Form.Item>
<Form.Item name="showTitle" valuePropName="checked" className="mb-2">
  <Checkbox>{t('opsAnalysis.screen.showTitle')}</Checkbox>
</Form.Item>
<Form.Item name="showClock" valuePropName="checked" className="mb-0">
  <Checkbox>{t('opsAnalysis.screen.showClock')}</Checkbox>
</Form.Item>
```

Add imports:

```ts
import { Button, Checkbox, Form, Input, InputNumber, Modal, message } from 'antd';
import type {
  ScreenDecorationsConfig,
  ScreenViewportConfig,
} from '@/app/ops-analysis/types/screen';
```

- [ ] **Step 4: Add locale strings**

Add to `web/src/app/ops-analysis/locales/zh.json` under `opsAnalysis.screen`:

```json
"defaultTitle": "网络运行态势大屏",
"addWidget": "添加组件",
"addThisWidget": "添加组件",
"screenTitle": "大屏标题",
"showTitle": "显示标题",
"showClock": "显示时钟",
"viewportContainsOverflow": "当前分辨率无法容纳已有组件，请先调整组件位置或尺寸",
"deleteWidget": "删除组件",
"editWidget": "配置组件",
"widgets": {
  "single": "单值卡",
  "gauge": "仪表盘",
  "line": "折线图",
  "bar": "柱状图",
  "pie": "饼图",
  "topN": "排行榜",
  "eventTable": "事件/告警流",
  "networkStatusTopology": "网络状态拓扑"
},
"widgetDescriptions": {
  "single": "展示核心 KPI、告警总数、在线率等关键数值",
  "gauge": "展示健康度、利用率、达成率等单指标状态",
  "line": "展示总体趋势和关键时间序列",
  "bar": "展示分类统计和对比分析",
  "pie": "展示占比和分布结构",
  "topN": "展示热点对象、异常对象和重点对象排行",
  "eventTable": "展示动态事件、告警流和最新状态",
  "networkStatusTopology": "展示只读网络关系和健康态"
}
```

Add matching English strings under `opsAnalysis.screen`:

```json
"defaultTitle": "Network Operations Screen",
"addWidget": "Add Widget",
"addThisWidget": "Add widget",
"screenTitle": "Screen Title",
"showTitle": "Show title",
"showClock": "Show clock",
"viewportContainsOverflow": "The selected resolution cannot contain existing widgets. Adjust widget positions or sizes first.",
"deleteWidget": "Delete widget",
"editWidget": "Configure widget",
"widgets": {
  "single": "KPI Card",
  "gauge": "Gauge",
  "line": "Line Chart",
  "bar": "Bar Chart",
  "pie": "Pie Chart",
  "topN": "Top N",
  "eventTable": "Event / Alert Stream",
  "networkStatusTopology": "Network Status Topology"
},
"widgetDescriptions": {
  "single": "Show key KPIs, alert totals, availability, and summary values",
  "gauge": "Show health, utilization, and target status",
  "line": "Show overall trends and time series",
  "bar": "Show category statistics and comparisons",
  "pie": "Show proportions and distribution",
  "topN": "Show hot, abnormal, or important ranked objects",
  "eventTable": "Show dynamic events, alert streams, and latest status",
  "networkStatusTopology": "Show read-only network relationships and health"
}
```

- [ ] **Step 5: Run type and locale checks**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add 'web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetSelector.tsx' 'web/src/app/ops-analysis/(pages)/view/screen/components/screenToolbar.tsx' 'web/src/app/ops-analysis/(pages)/view/screen/components/screenConfigModal.tsx' web/src/app/ops-analysis/locales/zh.json web/src/app/ops-analysis/locales/en.json
git commit -m "feat(ops-analysis): add screen editor controls"
```

## Task 6: Wire Screen Page Draft Editing, Save, Refresh, And Fullscreen

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`

- [ ] **Step 1: Add editor state**

Modify `screen/index.tsx` state:

```ts
const [editMode, setEditMode] = useState(false);
const [widgetSelectorOpen, setWidgetSelectorOpen] = useState(false);
const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
const [draftViewSets, setDraftViewSets] = useState<ScreenViewSets>(
  buildDefaultScreenViewSets,
);
const [refreshVersion, setRefreshVersion] = useState(0);
```

Keep `viewSets` as saved state and `savedViewSets` for dirty detection.

- [ ] **Step 2: Sync draft on load**

When a Screen loads successfully, set all three states:

```ts
const normalized = normalizeScreenViewSets(data?.view_sets);
setViewSets(normalized);
setSavedViewSets(normalized);
setDraftViewSets(normalized);
setEditMode(false);
setSelectedItemId(null);
```

When there is no selected screen, set all states to `buildDefaultScreenViewSets()`.

- [ ] **Step 3: Update dirty detection**

Use the draft in edit mode:

```ts
const activeViewSets = editMode ? draftViewSets : viewSets;
const hasUnsavedChanges = useCallback(
  () => editMode && JSON.stringify(draftViewSets) !== JSON.stringify(savedViewSets),
  [draftViewSets, editMode, savedViewSets],
);
```

- [ ] **Step 4: Add data source resolver**

Use the existing data source hook:

```ts
const dataSourceManager = useDataSourceManager();

useEffect(() => {
  if (selectedScreen?.data_id) {
    void dataSourceManager.fetchDataSources();
  }
}, [dataSourceManager, selectedScreen?.data_id]);

const dataSourceResolver = useCallback(
  (dataSource?: string | number) =>
    dataSourceManager.dataSources.find((item) => String(item.id) === String(dataSource)),
  [dataSourceManager.dataSources],
);
```

Import:

```ts
import { useDataSourceManager } from '@/app/ops-analysis/hooks/useDataSource';
```

- [ ] **Step 5: Add editing handlers**

Add handlers using layout utilities:

```ts
const handleAddWidget = (chartType: ScreenWidgetChartType) => {
  setDraftViewSets((current) => addScreenWidget(current, chartType));
  setWidgetSelectorOpen(false);
};

const handleMoveItem = (itemId: string, position: { x: number; y: number }) => {
  setDraftViewSets((current) => moveScreenItem(current, itemId, position));
};

const handleResizeItem = (itemId: string, size: { w: number; h: number }) => {
  setDraftViewSets((current) => resizeScreenItem(current, itemId, size));
};

const handleDeleteItem = (itemId: string) => {
  setDraftViewSets((current) => deleteScreenItem(current, itemId));
  setSelectedItemId((current) => (current === itemId ? null : current));
};

const handleRefresh = () => {
  setRefreshVersion((current) => current + 1);
};
```

Import:

```ts
import type { ScreenWidgetChartType } from '@/app/ops-analysis/types/screen';
import {
  addScreenWidget,
  canViewportContainItems,
  deleteScreenItem,
  moveScreenItem,
  resizeScreenItem,
  updateScreenItemConfig,
} from './utils/layout';
```

- [ ] **Step 6: Add edit/save/cancel**

Add:

```ts
const handleStartEdit = () => {
  setDraftViewSets(viewSets);
  setEditMode(true);
  setSelectedItemId(null);
};

const handleCancelEdit = () => {
  setDraftViewSets(savedViewSets);
  setEditMode(false);
  setSelectedItemId(null);
};

const handleSave = async () => {
  if (!selectedScreen?.data_id) return;

  setSaving(true);
  try {
    await saveScreen(selectedScreen.data_id, {
      name: selectedScreen.name,
      desc: selectedScreen.desc,
      groups: selectedScreen.groups,
      view_sets: draftViewSets,
    });
    setViewSets(draftViewSets);
    setSavedViewSets(draftViewSets);
    setEditMode(false);
    setSelectedItemId(null);
    message.success(t('opsAnalysis.screen.saveSuccess'));
  } catch (error) {
    console.error('Failed to save screen:', error);
    message.error(t('opsAnalysis.screen.saveFailed'));
  } finally {
    setSaving(false);
  }
};
```

- [ ] **Step 7: Update settings save**

Replace the existing viewport-only settings save:

```ts
const handleSaveSettings = async ({
  viewport,
  decorations,
}: {
  viewport: ScreenViewportConfig;
  decorations: ScreenDecorationsConfig;
}) => {
  const applySettings = (current: ScreenViewSets): ScreenViewSets => ({
    ...updateScreenViewport(current, viewport),
    decorations: {
      ...current.decorations,
      ...decorations,
    },
  });

  if (editMode) {
    setDraftViewSets((current) => applySettings(current));
    setSettingsOpen(false);
    return;
  }

  if (!selectedScreen?.data_id) return;
  const nextViewSets = applySettings(viewSets);
  setSaving(true);
  try {
    await saveScreen(selectedScreen.data_id, {
      name: selectedScreen.name,
      desc: selectedScreen.desc,
      groups: selectedScreen.groups,
      view_sets: nextViewSets,
    });
    setViewSets(nextViewSets);
    setSavedViewSets(nextViewSets);
    setDraftViewSets(nextViewSets);
    setSettingsOpen(false);
    message.success(t('opsAnalysis.screen.saveSuccess'));
  } catch (error) {
    console.error('Failed to save screen settings:', error);
    message.error(t('opsAnalysis.screen.saveFailed'));
  } finally {
    setSaving(false);
  }
};
```

Add:

```ts
const canSaveViewport = (viewport: ScreenViewportConfig) =>
  canViewportContainItems(activeViewSets.items, viewport);
```

- [ ] **Step 8: Wire render tree**

Update `ScreenCanvas` usage:

```tsx
<ScreenCanvas
  viewSets={activeViewSets}
  editMode={editMode}
  selectedItemId={selectedItemId}
  refreshVersion={refreshVersion}
  dataSourceResolver={dataSourceResolver}
  onSelectItem={setSelectedItemId}
  onMoveItem={handleMoveItem}
  onResizeItem={handleResizeItem}
  onDeleteItem={handleDeleteItem}
/>
```

Update toolbar:

```tsx
<ScreenToolbar
  selectedScreen={selectedScreen}
  editMode={editMode}
  saving={saving}
  onRefresh={handleRefresh}
  onOpenSettings={() => setSettingsOpen(true)}
  onOpenWidgetSelector={() => setWidgetSelectorOpen(true)}
  onPreview={enterFullscreen}
  onEdit={handleStartEdit}
  onCancel={handleCancelEdit}
  onSave={handleSave}
/>
```

Add selector and settings:

```tsx
<ScreenWidgetSelector
  open={widgetSelectorOpen}
  onCancel={() => setWidgetSelectorOpen(false)}
  onAdd={handleAddWidget}
/>
<ScreenConfigModal
  open={settingsOpen}
  viewport={activeViewSets.viewport}
  decorations={activeViewSets.decorations}
  saving={saving}
  canSaveViewport={canSaveViewport}
  onCancel={() => setSettingsOpen(false)}
  onSave={handleSaveSettings}
/>
```

Update fullscreen to render active draft when editing:

```tsx
<ScreenCanvas
  viewSets={activeViewSets}
  fullscreen
  refreshVersion={refreshVersion}
  dataSourceResolver={dataSourceResolver}
/>
```

- [ ] **Step 9: Run focused validation**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-layout
cd web && pnpm type-check
```

Expected: both PASS.

- [ ] **Step 10: Commit Task 6**

```bash
git add 'web/src/app/ops-analysis/(pages)/view/screen/index.tsx'
git commit -m "feat(ops-analysis): wire screen editor workflow"
```

## Task 7: Reuse Existing Widget Config For Screen Items

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`

- [ ] **Step 1: Import ViewConfig**

Add:

```ts
import ViewConfig from '@/app/ops-analysis/components/widgetConfig';
import type { WidgetConfig } from '@/app/ops-analysis/types/dashBoard';
```

- [ ] **Step 2: Add config drawer state**

Add:

```ts
const [configItemId, setConfigItemId] = useState<string | null>(null);
const currentConfigItem = useMemo(
  () => draftViewSets.items.find((item) => item.id === configItemId),
  [configItemId, draftViewSets.items],
);
```

- [ ] **Step 3: Open config from canvas**

Add:

```ts
const handleOpenItemConfig = (itemId: string) => {
  setSelectedItemId(itemId);
  setConfigItemId(itemId);
};
```

Pass it to ScreenCanvas:

```tsx
onEditItem={handleOpenItemConfig}
```

- [ ] **Step 4: Save widget config into Screen item**

Add:

```ts
const handleConfirmWidgetConfig = (values: WidgetConfig) => {
  if (!currentConfigItem) return;

  const nextItem = {
    ...currentConfigItem,
    title: values.name || currentConfigItem.title,
    config: {
      ...currentConfigItem.config,
      ...values,
      chartType: currentConfigItem.chartType,
      chartThemeMode: 'screen-dark' as const,
    },
  };
  setDraftViewSets((current) =>
    updateScreenItemConfig(current, currentConfigItem.id, nextItem),
  );
  setConfigItemId(null);
};
```

- [ ] **Step 5: Render ViewConfig**

Add near modals:

```tsx
{currentConfigItem && (
  <ViewConfig
    open={Boolean(configItemId)}
    item={{
      i: currentConfigItem.id,
      x: 0,
      y: 0,
      w: 1,
      h: 1,
      name: currentConfigItem.title || currentConfigItem.config?.name || currentConfigItem.chartType,
      valueConfig: {
        ...currentConfigItem.config,
        chartType: currentConfigItem.chartType,
        chartThemeMode: 'screen-dark',
      },
    }}
    showChartThemeMode={false}
    onConfirm={handleConfirmWidgetConfig}
    onClose={() => setConfigItemId(null)}
  />
)}
```

- [ ] **Step 6: Run type check and manual smoke**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS.

Manual smoke after the dev server is available:

1. Open an existing Screen.
2. Enter edit mode.
3. Add a single value widget.
4. Double-click or use the config entry to open `ViewConfig`.
5. Save a title.
6. Confirm the title appears in the Screen widget frame.

- [ ] **Step 7: Commit Task 7**

```bash
git add 'web/src/app/ops-analysis/(pages)/view/screen/index.tsx'
git commit -m "feat(ops-analysis): configure screen widgets"
```

## Task 8: Final Verification And Regression

**Files:**
- Modify only if verification finds issues in prior touched files.

- [ ] **Step 1: Run focused Screen tests**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-layout
```

Expected: PASS.

- [ ] **Step 2: Run type-check**

Run:

```bash
cd web && pnpm type-check
```

Expected: PASS.

- [ ] **Step 3: Run lint**

Run:

```bash
cd web && pnpm lint
```

Expected: PASS. If lint reports a Screen file touched by this plan, correct that file and rerun `cd web && pnpm lint` until the Screen-related lint output is clean.

- [ ] **Step 4: Run the dev server**

Run:

```bash
cd web && pnpm dev
```

Expected: Next.js starts on `http://localhost:3000`.

- [ ] **Step 5: Browser verification**

Using the browser, verify:

1. Screen page loads with a fixed-ratio technology-style canvas.
2. Toolbar buttons appear in Dashboard/Topology-style right-side placement.
3. Edit mode shows Add Widget, Cancel, Save.
4. Add `single`, `line`, `topN`, and `eventTable` widgets.
5. Drag and resize widgets; they do not leave the canvas.
6. Save, refresh page, and confirm layout persists.
7. View mode does not allow accidental drag.
8. Fullscreen preview hides editor controls and preserves Screen styling.
9. Dashboard page still uses normal Dashboard styling.
10. Topology page still uses normal Topology styling.

- [ ] **Step 6: Commit verification fixes**

If any fixes were required:

```bash
git add web/src/app/ops-analysis
git commit -m "fix(ops-analysis): polish screen editor verification"
```

If no fixes were required, do not create an empty commit.

## specs: 2026-06-30-ops-analysis-screen-mvp-interactions-design.md

日期：2026-06-30

## 背景

运营分析已经完成画布类型拆分的第一步，`screen` 和 `report` 已作为一等类型进入目录、API、前端路由和基础页面。当前大屏页面已经具备默认分辨率、分辨率配置、固定比例画布和全屏预览，但仍停留在空画布阶段，无法拖出真实可用的大屏。

本设计补齐 `Screen` 第一版 MVP 的交互需求。目标不是建设复杂大屏设计器，而是让用户可以在独立大屏画布中添加组件、配置数据、拖拽编排、保存并全屏展示，拖出来默认就是一屏好看的科技风值班大屏。

## 现状依据

仓库当前事实：

- `Screen` 和 `Report` 已新增为运营分析画布类型。证据：`server/apps/operation_analysis/models/models.py`、`server/apps/operation_analysis/urls.py`、`web/src/app/ops-analysis/constants/canvasTypes.ts`
- `Screen` 页面已有分辨率设置、固定比例画布和全屏预览。证据：`web/src/app/ops-analysis/(pages)/view/screen/index.tsx`、`web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`
- 现有通用组件渲染能力包含折线图、柱状图、饼图、单值卡、Gauge、TopN、事件表、网络状态拓扑等。证据：`web/src/app/ops-analysis/components/widgetRegistry.ts`、`web/src/app/ops-analysis/components/widgetRenderer.tsx`
- 仪表盘和拓扑图已经形成稳定操作习惯：右上角工具栏、圆形 icon button、tooltip、编辑态保存/取消、全屏退出按钮。证据：`web/src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardToolbar.tsx`、`web/src/app/ops-analysis/(pages)/view/topology/components/toolbar.tsx`

已确认产品决策：

- 大屏是面向值班总览、汇报展示和态势感知的展示画布。
- 大屏拥有固定分辨率和边界内编排规则。
- 大屏可以复用仪表盘图表和只读关系展示区块。
- 大屏不承接拓扑图的节点连线重编辑能力。
- 第一版尽量简单，除明确交互外不做复杂设计器能力。

## 目标

1. 让 `Screen` 能编辑真实大屏：添加组件、拖拽、缩放、配置数据、保存、查看和全屏预览。
2. 内置一套真实科技风大屏样式，让用户不配置样式也能拖出好看的大屏。
3. 复用现有组件数据渲染能力，避免重造图表数据链路。
4. 保持大屏样式私有，不污染 Dashboard、Topology 和通用 widget 默认样式。
5. 操作按钮位置、编辑态心智和全屏交互尽量参考现有仪表盘和拓扑图。

## 非目标

第一版不做以下能力：

- 自动布局
- 图层面板
- 批量选择
- 复制粘贴
- 撤销重做
- 键盘微调
- 快捷键体系
- 组件样式配置
- 多套主题切换
- 组件锁定/隐藏
- 自动缩放迁移布局
- 轮播
- 发布分享
- 多屏拼接
- 模板市场
- 拓扑节点连线编辑

## 推荐方案

采用“Screen 独立编排 + 复用 Dashboard widget 渲染”的方案。

`Screen` 拥有自己的固定分辨率画布、像素坐标布局、边界校验、全屏展示和科技风视觉系统。折线图、柱状图、饼图、单值卡、Gauge、TopN、事件表、网络状态拓扑等内容渲染复用现有 `WidgetRenderer` 和 widget 注册表。

不采用“Dashboard 换肤”方案，因为它容易变成暗色仪表盘，固定分辨率和像素级编排也会别扭。不采用“继续扩展 Topology/Architecture”方案，因为这会重新混淆大屏和关系画布边界。

## 架构边界

### Screen Canvas 层

负责固定分辨率画布：

- 读取 `view_sets.viewport.width` 和 `view_sets.viewport.height`
- 按目标分辨率展示画布边界
- 在页面容器和全屏容器中等比缩放
- 限制组件不能超出画布边界
- 承载内置背景、标题和时钟

组件坐标使用目标分辨率内的像素坐标，不使用 Dashboard 的 12 列流式网格。

### Screen Widget Frame 层

负责 Screen 私有科技风外框：

- 玻璃面板
- 发光边框
- 四角装饰
- 统一标题栏
- 告警强调色
- 科技线条和弱网格装饰

第一版不提供样式配置。用户添加组件后自动获得对应类型的大屏样式。

### Widget Renderer 内容层

继续复用现有 `WidgetRenderer` 和 widget 注册表，负责图表和数据内容。通用 widget 不直接承担大屏外框和装饰，不把大屏样式写入 Dashboard 或 Topology 的默认展示。

## 数据结构

`Screen.view_sets` 扩展为可编辑大屏文档：

```json
{
  "viewport": {
    "width": 1920,
    "height": 1080,
    "theme": "screen-tech-blue",
    "background": {
      "type": "builtIn",
      "key": "tech-grid"
    }
  },
  "items": [
    {
      "id": "widget-1",
      "type": "widget",
      "chartType": "single",
      "title": "告警总数",
      "x": 48,
      "y": 96,
      "w": 300,
      "h": 150,
      "zIndex": 1,
      "config": {}
    }
  ],
  "decorations": {
    "title": "网络运行态势大屏",
    "showTitle": true,
    "showClock": true
  }
}
```

字段说明：

- `viewport`：目标分辨率和内置大屏主题。第一版只使用内置主题，不提供主题选择。
- `items`：组件列表，坐标和尺寸均为目标分辨率内的像素值。
- `chartType`：组件类型，复用现有 widget 类型。
- `title`：组件展示标题。
- `config`：组件业务配置，尽量复用 Dashboard 的组件数据配置结构。
- `decorations`：画布级标题和时钟配置。

## 首批组件

第一版支持以下组件：

| 组件 | 用途 | 内置大屏样式 |
|---|---|---|
| 单值卡 | 核心 KPI、告警总数、在线率 | 大数字、弱单位、状态色、轻发光 |
| Gauge | 健康度、利用率、达成率 | 暗色仪表盘底、青蓝刻度、阈值高亮 |
| 折线图 | 趋势、时间序列 | 深色网格、霓虹线条、柔和面积光晕 |
| 柱状图 | 分类统计、对比 | 青蓝渐变柱、峰值高亮 |
| 饼图 | 占比、分布结构 | 环形图、中心信息增强 |
| TopN | 热点对象、异常排行 | 发光排行条、前三名强调、异常橙红 |
| 事件/告警流 | 动态事件、告警列表 | 纵向列表、等级色、最新事件高亮 |
| 网络状态拓扑区块 | 网络状态关系展示 | 只读关系块、健康态描边、异常节点高亮 |

网络状态拓扑区块只作为只读展示组件进入大屏，不提供节点连线编辑。

## 交互设计

### 页面框架

大屏页面继续采用运营分析已有操作骨架：

- 主体顶部显示大屏名称、描述、内置标记。
- 右上角显示工具栏。
- 图标按钮使用圆形按钮和 tooltip。
- 编辑态显示 `取消 / 保存`。
- 内置大屏禁用编辑入口。
- 全屏态隐藏页面工具栏，只保留退出全屏按钮。

### 查看态工具栏

查看态显示：

- `刷新`：手动刷新所有组件数据。
- `全屏预览`：进入展示态。
- `画布设置`：配置分辨率、标题、时钟。
- `编辑`：进入编辑态。

### 编辑态工具栏

编辑态显示：

- `刷新`：验证当前组件数据。
- `全屏预览`：预览当前编辑草稿，退出全屏后仍回到编辑态。
- `画布设置`：配置分辨率、标题、时钟。
- `添加组件`：打开组件选择面板。
- `取消`：丢弃草稿。
- `保存`：保存草稿。

第一版不做 `适配视图`，画布始终按当前容器可用空间等比缩放显示。

### 添加组件

点击 `添加组件` 后打开组件选择面板或弹窗。第一版组件选择只需满足：

- 展示首批组件列表。
- 每个组件有名称和简短用途说明。
- 选择后在画布可见区域插入默认尺寸组件。
- 组件插入后默认选中，便于马上配置数据。

默认尺寸按组件类型内置，例如单值卡较小、趋势图较宽、事件流较高、网络状态拓扑区块较大。

### 组件编排

编辑态支持：

- 拖拽移动
- 拖拽缩放
- 点击选中
- 删除组件
- 打开配置面板

边界规则：

- 组件 `x >= 0`
- 组件 `y >= 0`
- 组件 `x + w <= viewport.width`
- 组件 `y + h <= viewport.height`
- 组件 `w` 和 `h` 必须为正数

组件不能拖出画布边界，缩放也不能越界。

### 组件配置

选中组件后打开右侧配置抽屉或配置弹窗。第一版只配置业务内容：

- 标题
- 数据源
- 指标字段
- 展示字段
- 单位
- 值映射
- TopN 字段
- 事件/告警流字段
- 网络状态拓扑区块所需对象参数

具体字段以现有 Dashboard 组件配置可复用能力为准。第一版不提供组件样式配置。

### 画布设置

画布设置包含：

- 分辨率预设：`1920 x 1080`、`1366 x 768`、`3840 x 2160`
- 自定义宽高：正整数
- 大屏标题
- 是否显示标题
- 是否显示时钟

分辨率变更简单处理：

- 若新分辨率仍能容纳所有组件，允许保存。
- 若有组件越界，禁止保存并提示用户先调整组件位置或尺寸。
- 第一版不做自动布局迁移和等比缩放迁移。

### 保存与取消

进入编辑态时复制当前 `view_sets` 为草稿。

用户的添加、拖拽、缩放、删除和配置操作只修改草稿。点击保存时执行校验，校验通过后调用现有 `saveScreen` 写回。点击取消时丢弃草稿，恢复上次保存状态。

切换画布或离开页面时，沿用已有未保存确认逻辑。

### 全屏预览

全屏预览是展示态：

- 隐藏页面工具栏和编辑控件。
- 使用内置大屏背景、标题、时钟和组件样式。
- 按屏幕可用空间等比缩放。
- 保留退出全屏按钮。
- 不提供拖拽、缩放、配置、删除。

## 样式设计

第一版采用内置科技风，不给用户配置样式。目标是用户拖出组件后自然形成真实值班大屏，而不是普通仪表盘换黑底。

视觉方向：

- 暗色底色，避免纯黑，使用深蓝黑和弱网格建立空间感。
- 主色使用青蓝，辅助色使用蓝紫和冷白。
- 告警强调使用橙色和红色，但只用于异常信息。
- 面板为半透明深色玻璃，带轻微边框和角标装饰。
- 组件标题条统一，字号小而清晰，适合远距离观看。
- 图表背景、轴线和网格弱化，突出数据线、柱、排行条和关键数值。

隔离规则：

- 大屏样式写在 `Screen` 页面、`ScreenWidgetFrame` 或局部样式模块中。
- 样式类名前缀使用 `screen-` 或 CSS module 局部作用域。
- 不修改通用 widget 的默认卡片样式。
- 不让 Dashboard 和 Topology 默认使用 `screen-tech-blue` 或 `screen-dark`。
- 如通用图表需要大屏主题参数，只能由 Screen 渲染链路传入。

## 异常与空状态

- 未选择大屏：显示现有空状态。
- 大屏无组件：显示适合大屏的空状态，提示进入编辑态添加组件。
- 单个组件数据加载失败：只在该组件内显示错误态，不影响其他组件。
- 保存失败：保留草稿并提示保存失败。
- 分辨率变更导致越界：阻止保存并提示调整组件。
- 不支持的组件类型：显示组件不可用状态，不让整屏崩溃。

## 权限与内置对象

- 编辑入口继续受 `EditChart` 等现有权限控制。
- 内置大屏不可编辑时，禁用编辑按钮。
- 删除、新增、编辑大屏对象本身继续沿用现有目录和画布权限。
- 本设计不新增审批、发布或分享权限。

## 验收标准

功能验收：

1. 新建大屏后默认进入 `1920 x 1080` 固定分辨率画布。
2. 点击编辑后可以添加首批组件。
3. 组件可以在画布内拖拽和缩放。
4. 组件不能越过画布边界。
5. 组件可以打开配置面板完成数据配置。
6. 保存后刷新页面，大屏布局和组件配置仍能恢复。
7. 查看态不能误拖动组件。
8. 全屏预览按屏幕等比缩放，并保留大屏视觉。
9. 手动刷新可以触发组件重新取数。
10. 单个组件取数失败时，只显示该组件错误态，不影响整屏。

样式验收：

1. 大屏默认是暗色科技风，不是普通仪表盘换黑底。
2. 所有首批组件拖出后都有内置大屏样式。
3. 单值卡、Gauge、TopN、事件/告警流具有明显的大屏展示感。
4. 大屏样式只在 `Screen` 中生效，不改变 Dashboard 和 Topology 现有样式。
5. 操作按钮位置和交互习惯参考 Dashboard / Topology：右上角工具栏、tooltip、编辑态保存/取消、全屏退出按钮。

## 测试建议

纯函数测试：

- `view_sets` 归一化
- 组件坐标边界校验
- 添加组件默认尺寸
- 删除组件
- 更新组件位置和尺寸
- 分辨率变更越界判断

前端验证：

- 默认画布渲染
- 编辑态添加组件
- 拖拽缩放后保存结构正确
- 查看态不可拖动
- 全屏态等比缩放
- 单组件错误态不影响整屏

回归检查：

- Dashboard 图表样式不变。
- Topology 图表节点和关系画布样式不变。
- `screen` 样式不会通过全局 CSS 污染其他页面。

## 后续单独设计

- 多套大屏主题和样式配置
- 模板和模板市场
- 轮播
- 多屏拼接
- 发布分享
- 图层管理
- 复制粘贴和快捷键
- 自动布局和智能适配
