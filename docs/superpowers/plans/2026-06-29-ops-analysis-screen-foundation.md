# Ops Analysis Screen Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable Screen experience with default resolution, adjustable resolution, a fixed-ratio canvas, and fullscreen preview.

**Architecture:** Keep Screen separate from Topology and Dashboard. Put viewport defaults and validation in a pure utility, let Sidebar write the default `view_sets` when a Screen is created, and keep Screen page UI split into toolbar, config modal, and canvas components. This round does not add theme, background, title, clock, widget layout, or data binding.

**Tech Stack:** Next.js 16 + React 19 + TypeScript + Ant Design in `web/`; lightweight `tsx` scripts for focused logic tests; browser verification against `http://localhost:3000/ops-analysis/view`.

---

## Scope

In scope:

- Create Screen with default `1920 x 1080` viewport.
- Normalize old or empty Screen `view_sets` into `{ viewport, items, decorations }`.
- Allow Screen page users to edit resolution through presets or custom positive integers.
- Save updated resolution to `view_sets.viewport.width` and `view_sets.viewport.height`.
- Render a fixed-ratio canvas that scales within the available page area.
- Provide view-only fullscreen preview with the same fixed-ratio canvas.

Out of scope:

- Screen theme fields.
- Screen background fields.
- Title and clock decorations.
- Component add/drag/resize/data binding.
- Report work.
- Topology presentation cleanup.

## File Structure

- Modify `web/package.json`  
  Add a focused script for Screen viewport logic.
- Create `web/scripts/ops-analysis-screen-viewport-test.ts`  
  Tests pure Screen viewport defaults, normalization, validation, and create payload behavior.
- Modify `web/src/app/ops-analysis/types/index.ts`  
  Allow `ItemData.view_sets` for Screen creation.
- Modify `web/src/app/ops-analysis/types/screen.ts`  
  Remove current theme/background-first typing from the first-stage contract and define narrow viewport-oriented types.
- Create `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts`  
  Own default viewport, presets, normalization, validation, and immutable viewport updates.
- Modify `web/src/app/ops-analysis/components/sidebar.tsx`  
  Attach default Screen `view_sets` on create.
- Modify `web/src/app/ops-analysis/(pages)/view/components/basicCanvasPage.tsx`  
  Add an optional header action slot used by Screen toolbar.
- Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`  
  Fixed-ratio canvas renderer and empty state.
- Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenToolbar.tsx`  
  Settings and fullscreen actions.
- Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenConfigModal.tsx`  
  Preset/custom resolution form.
- Modify `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`  
  Wire load, save, dirty state, toolbar, config modal, fixed-ratio canvas, and fullscreen preview.
- Modify `web/src/app/ops-analysis/locales/zh.json`
- Modify `web/src/app/ops-analysis/locales/en.json`  
  Add Screen labels for settings, presets, validation, save, fullscreen, and empty canvas.

## Task 1: Viewport Contract And Tests

**Files:**

- Modify: `web/package.json`
- Create: `web/scripts/ops-analysis-screen-viewport-test.ts`
- Modify: `web/src/app/ops-analysis/types/screen.ts`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts`

- [ ] **Step 1: Add the failing viewport test script**

Add this script entry to `web/package.json` under `scripts`:

```json
"test:ops-analysis-screen-viewport": "pnpm exec tsx scripts/ops-analysis-screen-viewport-test.ts"
```

Create `web/scripts/ops-analysis-screen-viewport-test.ts`:

```ts
import assert from 'node:assert/strict';

import {
  DEFAULT_SCREEN_VIEW_SETS,
  DEFAULT_SCREEN_VIEWPORT,
  SCREEN_VIEWPORT_PRESETS,
  buildDefaultScreenViewSets,
  isValidViewportSize,
  normalizeScreenViewSets,
  updateScreenViewport,
} from '../src/app/ops-analysis/(pages)/view/screen/utils/viewport';

assert.deepEqual(DEFAULT_SCREEN_VIEWPORT, { width: 1920, height: 1080 });
assert.deepEqual(DEFAULT_SCREEN_VIEW_SETS, {
  viewport: { width: 1920, height: 1080 },
  items: [],
  decorations: {},
});

assert.equal(SCREEN_VIEWPORT_PRESETS.length, 3);
assert.deepEqual(SCREEN_VIEWPORT_PRESETS.map((item) => item.key), [
  '1920x1080',
  '1366x768',
  '3840x2160',
]);

assert.equal(isValidViewportSize(1920), true);
assert.equal(isValidViewportSize(1), true);
assert.equal(isValidViewportSize(0), false);
assert.equal(isValidViewportSize(-1), false);
assert.equal(isValidViewportSize(12.5), false);
assert.equal(isValidViewportSize(Number.NaN), false);

assert.deepEqual(normalizeScreenViewSets(null), DEFAULT_SCREEN_VIEW_SETS);
assert.deepEqual(normalizeScreenViewSets({}), DEFAULT_SCREEN_VIEW_SETS);
assert.deepEqual(
  normalizeScreenViewSets({
    viewport: { width: 1366, height: 768, theme: 'screen-dark' },
    items: [{ id: 'a' }],
    decorations: { showTitle: true },
  }),
  {
    viewport: { width: 1366, height: 768 },
    items: [{ id: 'a' }],
    decorations: {},
  },
);
assert.deepEqual(
  normalizeScreenViewSets({
    viewport: { width: 0, height: 0 },
    items: 'bad',
    decorations: null,
  }),
  DEFAULT_SCREEN_VIEW_SETS,
);

const defaultA = buildDefaultScreenViewSets();
const defaultB = buildDefaultScreenViewSets();
defaultA.viewport.width = 100;
assert.equal(defaultB.viewport.width, 1920);

const changed = updateScreenViewport(DEFAULT_SCREEN_VIEW_SETS, {
  width: 3840,
  height: 2160,
});
assert.deepEqual(changed, {
  viewport: { width: 3840, height: 2160 },
  items: [],
  decorations: {},
});
assert.deepEqual(DEFAULT_SCREEN_VIEW_SETS.viewport, { width: 1920, height: 1080 });

console.log('ops-analysis screen viewport tests passed');
```

- [ ] **Step 2: Run the test and confirm it fails**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-viewport
```

Expected: fails with a module resolution error for `screen/utils/viewport`.

- [ ] **Step 3: Narrow the Screen types**

Replace `web/src/app/ops-analysis/types/screen.ts` with:

```ts
import type { DirItem } from './index';

export interface ScreenViewportConfig {
  width: number;
  height: number;
}

export type ScreenItem = Record<string, unknown>;

export type ScreenDecorationsConfig = Record<string, never>;

export interface ScreenViewSets {
  viewport: ScreenViewportConfig;
  items: ScreenItem[];
  decorations: ScreenDecorationsConfig;
}

export interface ScreenProps {
  selectedScreen?: DirItem | null;
}
```

- [ ] **Step 4: Add viewport utility**

Create `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts`:

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
};

export const DEFAULT_SCREEN_DECORATIONS: ScreenDecorationsConfig = {};

export const DEFAULT_SCREEN_VIEW_SETS: ScreenViewSets = {
  viewport: { ...DEFAULT_SCREEN_VIEWPORT },
  items: [],
  decorations: DEFAULT_SCREEN_DECORATIONS,
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

export const buildDefaultScreenViewSets = (): ScreenViewSets => ({
  viewport: { ...DEFAULT_SCREEN_VIEWPORT },
  items: [],
  decorations: {},
});

export const normalizeScreenViewSets = (value: unknown): ScreenViewSets => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return buildDefaultScreenViewSets();
  }

  const source = value as Partial<ScreenViewSets>;
  const viewport = source.viewport || {};
  const width = isValidViewportSize(viewport.width)
    ? viewport.width
    : DEFAULT_SCREEN_VIEWPORT.width;
  const height = isValidViewportSize(viewport.height)
    ? viewport.height
    : DEFAULT_SCREEN_VIEWPORT.height;

  return {
    viewport: { width, height },
    items: Array.isArray(source.items) ? source.items : [],
    decorations: {},
  };
};

export const updateScreenViewport = (
  viewSets: ScreenViewSets,
  viewport: ScreenViewportConfig,
): ScreenViewSets => ({
  viewport: { width: viewport.width, height: viewport.height },
  items: [...viewSets.items],
  decorations: {},
});
```

- [ ] **Step 5: Run the viewport test**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-viewport
```

Expected: passes and prints `ops-analysis screen viewport tests passed`.

## Task 2: Default View Sets On Screen Creation

**Files:**

- Modify: `web/src/app/ops-analysis/types/index.ts`
- Modify: `web/src/app/ops-analysis/components/sidebar.tsx`
- Test: `web/scripts/ops-analysis-screen-viewport-test.ts`

- [ ] **Step 1: Extend create payload type**

In `web/src/app/ops-analysis/types/index.ts`, change `ItemData` to:

```ts
export interface ItemData {
  name: string;
  desc?: string;
  directory?: number;
  parent?: number | null;
  groups?: number[];
  view_sets?: unknown;
}
```

- [ ] **Step 2: Attach default Screen view_sets in Sidebar**

Add this import to `web/src/app/ops-analysis/components/sidebar.tsx`:

```ts
import { buildDefaultScreenViewSets } from '@/app/ops-analysis/(pages)/view/screen/utils/viewport';
```

Inside `handleSubmit`, after the `itemData` object is created with `name`, `desc`, and `groups`, and before directory/parent assignment, add:

```ts
if (newItemType === 'screen') {
  itemData.view_sets = buildDefaultScreenViewSets();
}
```

The create branch should read like this after the edit:

```ts
const itemData: ItemData = {
  name: values.name,
  desc: values.desc,
  groups: values.groups,
};

if (newItemType === 'screen') {
  itemData.view_sets = buildDefaultScreenViewSets();
}

if (modalAction === 'addChild' && currentDir?.data_id) {
  if (isCanvasType(newItemType)) {
    itemData.directory = parseInt(currentDir.data_id, 10);
  } else if (newItemType === 'directory') {
    itemData.parent = parseInt(currentDir.data_id, 10);
  }
} else if (newItemType === 'directory') {
  itemData.parent = null;
}
await createItem(newItemType, itemData);
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-viewport && pnpm test:ops-analysis-canvas-types
```

Expected: both scripts pass.

## Task 3: Screen Canvas Components

**Files:**

- Create: `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/components/screenToolbar.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/screen/components/screenConfigModal.tsx`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`

- [ ] **Step 1: Add Screen Canvas**

Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`:

```tsx
'use client';

import React from 'react';
import { Empty } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';

interface ScreenCanvasProps {
  viewSets: ScreenViewSets;
  fullscreen?: boolean;
}

const ScreenCanvas: React.FC<ScreenCanvasProps> = ({
  viewSets,
  fullscreen = false,
}) => {
  const { t } = useTranslation();
  const { width, height } = viewSets.viewport;

  return (
    <div
      className={`flex h-full w-full items-center justify-center overflow-hidden ${
        fullscreen
          ? 'bg-slate-950 p-4'
          : 'rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg-2)] p-6'
      }`}
    >
      <div
        className="relative max-h-full max-w-full overflow-hidden border border-cyan-400/60 bg-white shadow-sm"
        style={{ aspectRatio: `${width} / ${height}`, width: '100%' }}
      >
        <div className="absolute left-3 top-3 rounded bg-black/55 px-2 py-1 text-xs font-medium text-white">
          {width} × {height}
        </div>
        <div className="flex h-full w-full items-center justify-center p-8">
          <Empty
            description={
              <span className="text-[var(--color-text-3)]">
                {t('opsAnalysis.screen.canvasEmpty')}
              </span>
            }
          />
        </div>
      </div>
    </div>
  );
};

export default ScreenCanvas;
```

- [ ] **Step 2: Add Screen Toolbar**

Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenToolbar.tsx`:

```tsx
'use client';

import React from 'react';
import { Button, Space, Tooltip } from 'antd';
import { FullscreenOutlined, SettingOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';

interface ScreenToolbarProps {
  onOpenSettings: () => void;
  onPreview: () => void;
  saving?: boolean;
}

const ScreenToolbar: React.FC<ScreenToolbarProps> = ({
  onOpenSettings,
  onPreview,
  saving = false,
}) => {
  const { t } = useTranslation();

  return (
    <Space>
      <Tooltip title={t('opsAnalysis.screen.canvasSettings')}>
        <Button
          icon={<SettingOutlined />}
          loading={saving}
          onClick={onOpenSettings}
        />
      </Tooltip>
      <Tooltip title={t('opsAnalysis.screen.fullscreenPreview')}>
        <Button icon={<FullscreenOutlined />} onClick={onPreview} />
      </Tooltip>
    </Space>
  );
};

export default ScreenToolbar;
```

- [ ] **Step 3: Add Screen Config Modal**

Create `web/src/app/ops-analysis/(pages)/view/screen/components/screenConfigModal.tsx`:

```tsx
'use client';

import React, { useEffect } from 'react';
import { Form, InputNumber, Modal, Radio, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';
import type { ScreenViewportConfig } from '@/app/ops-analysis/types/screen';
import {
  SCREEN_VIEWPORT_PRESETS,
  isValidViewportSize,
} from '../utils/viewport';

interface ScreenConfigModalProps {
  open: boolean;
  viewport: ScreenViewportConfig;
  saving?: boolean;
  onCancel: () => void;
  onSave: (viewport: ScreenViewportConfig) => void;
}

interface ScreenConfigFormValues {
  preset: string;
  width: number;
  height: number;
}

const getPresetKey = (viewport: ScreenViewportConfig) =>
  SCREEN_VIEWPORT_PRESETS.find(
    (item) => item.width === viewport.width && item.height === viewport.height,
  )?.key || 'custom';

const ScreenConfigModal: React.FC<ScreenConfigModalProps> = ({
  open,
  viewport,
  saving = false,
  onCancel,
  onSave,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<ScreenConfigFormValues>();
  const preset = Form.useWatch('preset', form);

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      preset: getPresetKey(viewport),
      width: viewport.width,
      height: viewport.height,
    });
  }, [form, open, viewport]);

  const handlePresetChange = (key: string) => {
    const selected = SCREEN_VIEWPORT_PRESETS.find((item) => item.key === key);
    if (!selected) return;
    form.setFieldsValue({
      preset: selected.key,
      width: selected.width,
      height: selected.height,
    });
  };

  const handleOk = async () => {
    const values = await form.validateFields();
    onSave({ width: values.width, height: values.height });
  };

  return (
    <Modal
      title={t('opsAnalysis.screen.canvasSettings')}
      open={open}
      confirmLoading={saving}
      onCancel={onCancel}
      onOk={handleOk}
      okText={t('common.save')}
      cancelText={t('common.cancel')}
      centered
    >
      <Form form={form} layout="vertical">
        <Form.Item name="preset" label={t('opsAnalysis.screen.resolutionPreset')}>
          <Radio.Group onChange={(event) => handlePresetChange(event.target.value)}>
            <Space direction="vertical">
              {SCREEN_VIEWPORT_PRESETS.map((item) => (
                <Radio key={item.key} value={item.key}>
                  {item.label}
                </Radio>
              ))}
              <Radio value="custom">{t('opsAnalysis.screen.customResolution')}</Radio>
            </Space>
          </Radio.Group>
        </Form.Item>
        <Space className="w-full" size={12}>
          <Form.Item
            name="width"
            label={t('opsAnalysis.screen.width')}
            rules={[
              {
                validator: (_, value) =>
                  isValidViewportSize(value)
                    ? Promise.resolve()
                    : Promise.reject(new Error(t('opsAnalysis.screen.sizeInvalid'))),
              },
            ]}
          >
            <InputNumber
              min={1}
              precision={0}
              disabled={preset !== 'custom'}
              className="w-full"
            />
          </Form.Item>
          <Form.Item
            name="height"
            label={t('opsAnalysis.screen.height')}
            rules={[
              {
                validator: (_, value) =>
                  isValidViewportSize(value)
                    ? Promise.resolve()
                    : Promise.reject(new Error(t('opsAnalysis.screen.sizeInvalid'))),
              },
            ]}
          >
            <InputNumber
              min={1}
              precision={0}
              disabled={preset !== 'custom'}
              className="w-full"
            />
          </Form.Item>
        </Space>
      </Form>
    </Modal>
  );
};

export default ScreenConfigModal;
```

- [ ] **Step 4: Add locale keys**

In `web/src/app/ops-analysis/locales/zh.json`, update `opsAnalysis.screen` to include:

```json
"basicShellDesc": "大屏用于固定比例展示视图，本轮支持分辨率配置、画布边界和全屏预览。",
"viewport": "画布尺寸",
"itemCount": "组件数",
"canvasSettings": "画布设置",
"fullscreenPreview": "全屏预览",
"resolutionPreset": "分辨率预设",
"customResolution": "自定义分辨率",
"width": "宽度",
"height": "高度",
"sizeInvalid": "请输入正整数",
"saveSuccess": "大屏配置已保存",
"saveFailed": "大屏配置保存失败",
"canvasEmpty": "组件编排能力后续补充"
```

Remove the `theme` key from `opsAnalysis.screen` if no other current file references it after Task 4.

In `web/src/app/ops-analysis/locales/en.json`, update `opsAnalysis.screen` to include:

```json
"basicShellDesc": "Screens are fixed-ratio display views. This round supports resolution settings, canvas bounds, and fullscreen preview.",
"viewport": "Canvas Size",
"itemCount": "Items",
"canvasSettings": "Canvas Settings",
"fullscreenPreview": "Fullscreen Preview",
"resolutionPreset": "Resolution Preset",
"customResolution": "Custom Resolution",
"width": "Width",
"height": "Height",
"sizeInvalid": "Enter a positive integer",
"saveSuccess": "Screen settings saved",
"saveFailed": "Failed to save screen settings",
"canvasEmpty": "Widget composition will be added in a future iteration"
```

Remove the `theme` key from `opsAnalysis.screen` if no other current file references it after Task 4.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-viewport
```

Expected: passes.

## Task 4: Screen Page Wiring And Save Flow

**Files:**

- Modify: `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/components/basicCanvasPage.tsx`
- Test: `web/scripts/ops-analysis-screen-viewport-test.ts`

- [ ] **Step 1: Wire Screen page state and actions**

Replace `web/src/app/ops-analysis/(pages)/view/screen/index.tsx` with:

```tsx
'use client';

import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState,
} from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useScreenApi } from '@/app/ops-analysis/api/screen';
import type {
  ScreenProps,
  ScreenViewSets,
  ScreenViewportConfig,
} from '@/app/ops-analysis/types/screen';
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '@/app/ops-analysis/components/appFullscreen';
import BasicCanvasPage from '../components/basicCanvasPage';
import ScreenCanvas from './components/screenCanvas';
import ScreenConfigModal from './components/screenConfigModal';
import ScreenToolbar from './components/screenToolbar';
import {
  buildDefaultScreenViewSets,
  normalizeScreenViewSets,
  updateScreenViewport,
} from './utils/viewport';

export interface ScreenRef {
  hasUnsavedChanges: () => boolean;
}

const Screen = forwardRef<ScreenRef, ScreenProps>(({ selectedScreen }, ref) => {
  const { t } = useTranslation();
  const { getScreenDetail, saveScreen } = useScreenApi();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [viewSets, setViewSets] = useState<ScreenViewSets>(
    buildDefaultScreenViewSets,
  );
  const [savedViewSets, setSavedViewSets] = useState<ScreenViewSets>(
    buildDefaultScreenViewSets,
  );
  const { isFullscreen, enterFullscreen, exitFullscreen } = useAppViewFullscreen();

  const hasUnsavedChanges = useCallback(
    () => JSON.stringify(viewSets) !== JSON.stringify(savedViewSets),
    [savedViewSets, viewSets],
  );

  useImperativeHandle(ref, () => ({
    hasUnsavedChanges,
  }));

  useEffect(() => {
    const screenId = selectedScreen?.data_id;
    if (!screenId) {
      const emptyViewSets = buildDefaultScreenViewSets();
      setViewSets(emptyViewSets);
      setSavedViewSets(emptyViewSets);
      return;
    }

    let cancelled = false;
    setLoading(true);
    getScreenDetail(screenId)
      .then((data) => {
        if (cancelled) return;
        const normalized = normalizeScreenViewSets(data?.view_sets);
        setViewSets(normalized);
        setSavedViewSets(normalized);
      })
      .catch((error) => {
        console.error('Failed to load screen:', error);
        if (!cancelled) {
          const fallback = buildDefaultScreenViewSets();
          setViewSets(fallback);
          setSavedViewSets(fallback);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [getScreenDetail, selectedScreen?.data_id]);

  const handleSaveViewport = async (viewport: ScreenViewportConfig) => {
    if (!selectedScreen?.data_id) return;

    const nextViewSets = updateScreenViewport(viewSets, viewport);
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
      setSettingsOpen(false);
      message.success(t('opsAnalysis.screen.saveSuccess'));
    } catch (error) {
      console.error('Failed to save screen viewport:', error);
      message.error(t('opsAnalysis.screen.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const stats = useMemo(
    () => [
      {
        label: t('opsAnalysis.screen.viewport'),
        value: `${viewSets.viewport.width} × ${viewSets.viewport.height}`,
      },
      {
        label: t('opsAnalysis.screen.itemCount'),
        value: viewSets.items.length,
      },
    ],
    [t, viewSets],
  );

  if (isFullscreen) {
    return (
      <div className="fixed inset-0 z-[1000] bg-slate-950">
        <AppViewFullscreenExit visible onExit={exitFullscreen} />
        <ScreenCanvas viewSets={viewSets} fullscreen />
      </div>
    );
  }

  return (
    <>
      <BasicCanvasPage
        selectedItem={selectedScreen}
        loading={loading}
        titleFallback={t('opsAnalysis.screen.title')}
        emptyDescription={t('opsAnalysis.screen.selectFirst')}
        description={t('opsAnalysis.screen.basicShellDesc')}
        stats={stats}
        extra={
          <ScreenToolbar
            saving={saving}
            onOpenSettings={() => setSettingsOpen(true)}
            onPreview={enterFullscreen}
          />
        }
      >
        <ScreenCanvas viewSets={viewSets} />
      </BasicCanvasPage>
      <ScreenConfigModal
        open={settingsOpen}
        viewport={viewSets.viewport}
        saving={saving}
        onCancel={() => setSettingsOpen(false)}
        onSave={handleSaveViewport}
      />
    </>
  );
});

Screen.displayName = 'Screen';

export default Screen;
```

- [ ] **Step 2: Add `extra` support to BasicCanvasPage**

Modify `web/src/app/ops-analysis/(pages)/view/components/basicCanvasPage.tsx`:

```ts
interface BasicCanvasPageProps {
  selectedItem?: DirItem | null;
  loading?: boolean;
  titleFallback: string;
  emptyDescription: string;
  description?: string;
  stats?: StatItem[];
  children?: React.ReactNode;
  extra?: React.ReactNode;
}
```

Include `extra` in destructuring:

```ts
const BasicCanvasPage: React.FC<BasicCanvasPageProps> = ({
  selectedItem,
  loading = false,
  titleFallback,
  emptyDescription,
  description,
  stats = [],
  children,
  extra,
}) => {
```

Render it in the header action area:

```tsx
<div className="flex shrink-0 items-center gap-2">{extra}</div>
```

Place that `div` immediately after the existing title/description block and before the closing tag of the header row:

```tsx
{extra && <div className="flex shrink-0 items-center gap-2">{extra}</div>}
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-viewport && pnpm test:ops-analysis-canvas-types
```

Expected: both scripts pass.

## Task 5: Browser Verification

**Files:**

- No planned source edits in this task.

- [ ] **Step 1: Start or reuse the web dev server**

Run:

```bash
cd web && pnpm dev
```

Expected: dev server is reachable at `http://localhost:3000`.

- [ ] **Step 2: Open the app and authenticate**

Open:

```text
http://localhost:3000/ops-analysis/view
```

Use:

```text
username: admin
password: password
```

Expected: the ops-analysis view loads and the directory tree is visible.

- [ ] **Step 3: Create a Screen under a directory**

Use the sidebar create menu to create a Screen.

Expected:

- The created Screen is selectable in the directory tree.
- The page shows `1920 × 1080` in the stats area.
- The canvas boundary is visible.
- The canvas empty state says component composition is not part of this round.

- [ ] **Step 4: Change resolution through settings**

Click Screen settings, choose `1366 × 768`, save.

Expected:

- Save succeeds.
- The stats area updates to `1366 × 768`.
- Reloading the same Screen keeps `1366 × 768`.

- [ ] **Step 5: Validate custom size rules**

Open settings, choose custom resolution, enter `0` for width and `1080` for height, then save.

Expected:

- The modal blocks save.
- The validation message says the value must be a positive integer.

Then enter `1600` and `900`, save.

Expected:

- Save succeeds.
- The stats area updates to `1600 × 900`.
- The canvas ratio visibly changes to 16:9.

- [ ] **Step 6: Verify fullscreen preview**

Click fullscreen preview.

Expected:

- App chrome and Screen settings controls disappear.
- Only the Screen canvas is shown on a dark fullscreen surface.
- The canvas remains fixed ratio and centered.
- The exit fullscreen button returns to the normal page.

## Task 6: Final Verification

**Files:**

- No planned source edits in this task.

- [ ] **Step 1: Run focused automated checks**

Run:

```bash
cd web && pnpm test:ops-analysis-screen-viewport && pnpm test:ops-analysis-canvas-types
```

Expected: both scripts pass.

- [ ] **Step 2: Run TypeScript check if time allows**

Run:

```bash
cd web && pnpm type-check
```

Expected: either passes, or fails only on pre-existing unrelated TypeScript issues. If it fails, record the first unrelated file path and error code in the implementation summary.

- [ ] **Step 3: Inspect source for excluded fields**

Run:

```bash
rg -n "screen-dark|screen-light|background|theme|showTitle|showClock" web/src/app/ops-analysis/\(pages\)/view/screen web/src/app/ops-analysis/types/screen.ts
```

Expected: no matches in Screen first-stage source files.

- [ ] **Step 4: Inspect changed files**

Run:

```bash
git diff -- web/package.json web/scripts/ops-analysis-screen-viewport-test.ts web/src/app/ops-analysis/types/index.ts web/src/app/ops-analysis/types/screen.ts web/src/app/ops-analysis/components/sidebar.tsx web/src/app/ops-analysis/\(pages\)/view/components/basicCanvasPage.tsx web/src/app/ops-analysis/\(pages\)/view/screen web/src/app/ops-analysis/locales/zh.json web/src/app/ops-analysis/locales/en.json
```

Expected: diff only contains Screen first-stage work and locale labels needed for that work.

## Self-Review

- Spec coverage: the plan covers default resolution, adjustable resolution, fixed-ratio canvas, fullscreen preview, save/load behavior, and excludes theme/background/title/clock/widget binding.
- Placeholder scan: no task relies on an unspecified file, missing function name, or unspecified validation behavior.
- Type consistency: `ScreenViewSets`, `ScreenViewportConfig`, `buildDefaultScreenViewSets`, `normalizeScreenViewSets`, and `updateScreenViewport` are defined before use.
- Scope check: this is intentionally separate from the broader canvas split plan so the first Screen interaction can ship without Report or Topology cleanup.
