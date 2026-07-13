# Ops Analysis Screen Unified Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给运营分析大屏补齐与仪表盘、拓扑一致的统一筛选和命名空间查询上下文。

**Architecture:** 抽一个小型公共查询状态层，承载筛选定义/筛选值同步和命名空间草稿/已应用状态。大屏 `view_sets` 持久化筛选定义，运行态筛选值和命名空间只存在页面状态，并一路透传到 `WidgetWrapper`。

**Tech Stack:** Next.js 16, React 19, TypeScript, Ant Design, existing ops-analysis unified filter components.

---

## File Structure

- Create `web/src/app/ops-analysis/hooks/useOpsAnalysisQueryState.ts`
  - 统一管理筛选定义、草稿筛选值、已应用筛选值、命名空间草稿/已应用值和搜索版本号。
- Create `web/src/app/ops-analysis/utils/unifiedFilterState.ts`
  - 放纯函数：筛选定义规范化、筛选值同步、相对时间默认值规范化。
- Modify `web/src/app/ops-analysis/utils/canvasResources.ts`
  - 增加 screen 数据源和命名空间收集工具，避免大屏单独写一套。
- Modify `web/src/app/ops-analysis/types/screen.ts`
  - 给 `ScreenViewSets` 增加可选 `filters` 字段。
- Modify `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts`
  - 默认大屏和规范化逻辑保留 `filters`。
- Modify `web/src/app/ops-analysis/(pages)/view/screen/utils/layout.ts`
  - 组件新增、编辑、删除后保留或重建筛选定义，并提供清理无效绑定的工具。
- Modify `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`
  - 接入公共 query state，显示统一筛选条/命名空间选择器，打开筛选配置弹窗，保存/取消同步筛选定义。
- Modify `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`
  - 增加查询上下文 props 并透传。
- Modify `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetRenderer.tsx`
  - 将筛选定义、已应用筛选值、命名空间和版本号传给 `WidgetWrapper`。
- Modify `web/src/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync.ts`
  - 只把重复的 `syncFilterValuesForDefinitions` 替换成公共纯函数；不重构页面状态。
- Modify `web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts`
  - 只把重复的 `syncFilterValuesWithDefinitions` 替换成公共纯函数；不重构拓扑状态。

## Task 1: Shared Filter State Utilities

**Files:**
- Create: `web/src/app/ops-analysis/utils/unifiedFilterState.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts`

- [ ] **Step 1: Create the shared utility file**

Create `web/src/app/ops-analysis/utils/unifiedFilterState.ts` with these exports:

```ts
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import { normalizeTimeRangeFilterValue } from '@/app/ops-analysis/utils/filterValue';

export const normalizeStoredFilterDefinitions = (
  rawFilters: unknown,
): UnifiedFilterDefinition[] => {
  if (Array.isArray(rawFilters)) {
    return rawFilters as UnifiedFilterDefinition[];
  }
  if (!rawFilters || typeof rawFilters !== 'object') {
    return [];
  }
  const candidate = rawFilters as {
    definitions?: unknown;
    unifiedFilters?: unknown;
  };
  if (Array.isArray(candidate.definitions)) {
    return candidate.definitions as UnifiedFilterDefinition[];
  }
  if (Array.isArray(candidate.unifiedFilters)) {
    return candidate.unifiedFilters as UnifiedFilterDefinition[];
  }
  return [];
};

export const syncFilterValuesWithDefinitions = (
  nextDefinitions: UnifiedFilterDefinition[],
  currentValues: Record<string, FilterValue>,
): Record<string, FilterValue> => {
  const allowedIds = new Set(nextDefinitions.map((definition) => definition.id));
  const updatedValues = Object.entries(currentValues).reduce<
    Record<string, FilterValue>
  >((acc, [filterId, value]) => {
    if (allowedIds.has(filterId)) {
      acc[filterId] = value;
    }
    return acc;
  }, {});

  nextDefinitions.forEach((definition) => {
    const hasValue =
      updatedValues[definition.id] !== undefined &&
      updatedValues[definition.id] !== null;
    if (!definition.enabled || hasValue) return;
    if (
      definition.defaultValue === undefined ||
      definition.defaultValue === null
    ) {
      return;
    }
    if (definition.type === 'timeRange') {
      const normalizedValue = normalizeTimeRangeFilterValue(
        definition.defaultValue,
      );
      if (normalizedValue) {
        updatedValues[definition.id] = normalizedValue;
      }
      return;
    }
    updatedValues[definition.id] = definition.defaultValue;
  });

  return updatedValues;
};
```

- [ ] **Step 2: Update dashboard to import the shared sync helper**

In `web/src/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync.ts`, replace the local `syncFilterValuesForDefinitions` implementation body with an import alias:

```ts
import {
  syncFilterValuesWithDefinitions as syncFilterValuesForDefinitions,
} from '@/app/ops-analysis/utils/unifiedFilterState';
```

Remove the now-unused `normalizeTimeRangeFilterValue` import from this file.

- [ ] **Step 3: Update topology to import the shared sync helper**

In `web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts`, replace the local `syncFilterValuesWithDefinitions` implementation with:

```ts
import {
  syncFilterValuesWithDefinitions,
} from '@/app/ops-analysis/utils/unifiedFilterState';
```

Remove the now-unused `normalizeTimeRangeFilterValue` import from this file.

- [ ] **Step 4: Type-check the shared extraction**

Run:

```bash
cd web && pnpm type-check
```

Expected: no new errors in the touched ops-analysis files. If the repo still has unrelated existing type errors, record them and continue only after confirming they are unchanged.

## Task 2: Shared Query State Hook

**Files:**
- Create: `web/src/app/ops-analysis/hooks/useOpsAnalysisQueryState.ts`

- [ ] **Step 1: Create the query state hook**

Create `web/src/app/ops-analysis/hooks/useOpsAnalysisQueryState.ts`:

```ts
import { useCallback, useState } from 'react';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import { syncFilterValuesWithDefinitions } from '@/app/ops-analysis/utils/unifiedFilterState';

interface QuerySnapshot {
  definitions: UnifiedFilterDefinition[];
  filterValues: Record<string, FilterValue>;
  appliedFilterValues: Record<string, FilterValue>;
  namespaceDraftId?: number;
  appliedNamespaceId?: number;
}

export const useOpsAnalysisQueryState = () => {
  const [definitions, setDefinitionsState] = useState<
    UnifiedFilterDefinition[]
  >([]);
  const [filterValues, setFilterValuesState] = useState<
    Record<string, FilterValue>
  >({});
  const [appliedFilterValues, setAppliedFilterValuesState] = useState<
    Record<string, FilterValue>
  >({});
  const [namespaceDraftId, setNamespaceDraftId] = useState<number | undefined>();
  const [appliedNamespaceId, setAppliedNamespaceId] = useState<
    number | undefined
  >();
  const [filterSearchVersion, setFilterSearchVersion] = useState(0);
  const [namespaceSearchVersion, setNamespaceSearchVersion] = useState(0);

  const resetQueryState = useCallback((snapshot?: Partial<QuerySnapshot>) => {
    const nextDefinitions = snapshot?.definitions ?? [];
    const nextValues = syncFilterValuesWithDefinitions(
      nextDefinitions,
      snapshot?.filterValues ?? {},
    );
    const nextAppliedValues = syncFilterValuesWithDefinitions(
      nextDefinitions,
      snapshot?.appliedFilterValues ?? nextValues,
    );
    setDefinitionsState(nextDefinitions);
    setFilterValuesState(nextValues);
    setAppliedFilterValuesState(nextAppliedValues);
    setNamespaceDraftId(snapshot?.namespaceDraftId);
    setAppliedNamespaceId(snapshot?.appliedNamespaceId);
    setFilterSearchVersion(0);
    setNamespaceSearchVersion(0);
  }, []);

  const setDefinitions = useCallback(
    (nextDefinitions: UnifiedFilterDefinition[]) => {
      setDefinitionsState(nextDefinitions);
      setFilterValuesState((current) =>
        syncFilterValuesWithDefinitions(nextDefinitions, current),
      );
      setAppliedFilterValuesState((current) =>
        syncFilterValuesWithDefinitions(nextDefinitions, current),
      );
    },
    [],
  );

  const setFilterValues = useCallback(
    (values: Record<string, FilterValue>) => {
      setFilterValuesState({ ...values });
    },
    [],
  );

  const applyFilters = useCallback(
    (values: Record<string, FilterValue>) => {
      const nextValues = syncFilterValuesWithDefinitions(definitions, values);
      setFilterValuesState(nextValues);
      setAppliedFilterValuesState(nextValues);
      setFilterSearchVersion((current) => current + 1);
    },
    [definitions],
  );

  const applyNamespace = useCallback((namespaceId: number | undefined) => {
    setNamespaceDraftId(namespaceId);
    setAppliedNamespaceId(namespaceId);
    setNamespaceSearchVersion((current) => current + 1);
  }, []);

  const applyQuery = useCallback(
    (values: Record<string, FilterValue>, namespaceId: number | undefined) => {
      const nextValues = syncFilterValuesWithDefinitions(definitions, values);
      setFilterValuesState(nextValues);
      setAppliedFilterValuesState(nextValues);
      setNamespaceDraftId(namespaceId);
      setAppliedNamespaceId(namespaceId);
      setFilterSearchVersion((current) => current + 1);
      setNamespaceSearchVersion((current) => current + 1);
    },
    [definitions],
  );

  return {
    definitions,
    filterValues,
    appliedFilterValues,
    namespaceDraftId,
    appliedNamespaceId,
    filterSearchVersion,
    namespaceSearchVersion,
    setDefinitions,
    setFilterValues,
    setNamespaceDraftId,
    setAppliedNamespaceId,
    resetQueryState,
    applyFilters,
    applyNamespace,
    applyQuery,
  };
};
```

- [ ] **Step 2: Type-check the new hook**

Run:

```bash
cd web && pnpm type-check
```

Expected: the hook compiles. Existing unrelated type errors may still appear.

## Task 3: Screen Types, Normalization, and Resources

**Files:**
- Modify: `web/src/app/ops-analysis/types/screen.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts`
- Modify: `web/src/app/ops-analysis/utils/canvasResources.ts`

- [ ] **Step 1: Add screen filters to the type**

In `web/src/app/ops-analysis/types/screen.ts`, import the filter type and extend `ScreenViewSets`:

```ts
import type { UnifiedFilterDefinition, ValueConfig } from './dashBoard';
```

```ts
export interface ScreenViewSets {
  viewport: ScreenViewportConfig;
  items: ScreenItem[];
  decorations: ScreenDecorationsConfig;
  filters?: UnifiedFilterDefinition[];
}
```

- [ ] **Step 2: Preserve filters in default and normalized screen view sets**

In `web/src/app/ops-analysis/(pages)/view/screen/utils/viewport.ts`, import:

```ts
import { normalizeStoredFilterDefinitions } from '@/app/ops-analysis/utils/unifiedFilterState';
```

Add `filters: []` to `DEFAULT_SCREEN_VIEW_SETS` and `buildDefaultScreenViewSets`.

In `normalizeScreenViewSets`, return:

```ts
return {
  viewport: {
    width,
    height,
    background: DEFAULT_SCREEN_VIEWPORT.background
      ? { ...DEFAULT_SCREEN_VIEWPORT.background }
      : undefined,
    theme: DEFAULT_SCREEN_VIEWPORT.theme,
  },
  items: Array.isArray(source.items) ? source.items : [],
  decorations,
  filters: normalizeStoredFilterDefinitions(source.filters),
};
```

In `updateScreenViewport`, preserve filters:

```ts
filters: [...(viewSets.filters ?? [])],
```

- [ ] **Step 3: Add screen resource helpers**

In `web/src/app/ops-analysis/utils/canvasResources.ts`, import `ScreenViewSets` and add:

```ts
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
```

```ts
export const collectScreenDataSourceIds = (viewSets: ScreenViewSets) => {
  const ids = new Set<number>();
  viewSets.items.forEach((item) => {
    const rawId = item.config?.dataSource;
    const normalizedId =
      typeof rawId === 'string' ? parseInt(rawId, 10) : rawId;
    if (Number.isFinite(normalizedId)) {
      ids.add(normalizedId as number);
    }
  });
  return Array.from(ids);
};

export const collectScreenNamespaceIds = (
  viewSets: ScreenViewSets,
  dataSources: DatasourceItem[] = [],
) => {
  const namespaceIds = new Set<number>();
  viewSets.items.forEach((item) => {
    const rawId = item.config?.dataSource;
    const normalizedId =
      typeof rawId === 'string' ? parseInt(rawId, 10) : rawId;
    const dataSource = dataSources.find((source) => source.id === normalizedId);
    dataSource?.namespaces?.forEach((id) => namespaceIds.add(id));
  });
  return namespaceIds;
};
```

- [ ] **Step 4: Type-check screen normalization**

Run:

```bash
cd web && pnpm type-check
```

Expected: screen types compile.

## Task 4: Screen Filter Rebuild and Binding Cleanup

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/utils/layout.ts`

- [ ] **Step 1: Add helpers to rebuild screen filters**

In `layout.ts`, import:

```ts
import type {
  FilterBindings,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import {
  buildDefaultFilterBindings,
  getFilterDefinitionId,
} from '@/app/ops-analysis/utils/widgetDataTransform';
```

Add helpers:

```ts
const resolveScreenWidgetParams = (
  item: ScreenWidgetItem,
  dataSource?: DatasourceItem,
) => {
  const widgetParams = item.config?.dataSourceParams;
  return Array.isArray(widgetParams) && widgetParams.length > 0
    ? widgetParams
    : dataSource?.params;
};

export const buildFiltersFromScreenItems = ({
  viewSets,
  previousDefinitions,
  dataSources,
}: {
  viewSets: ScreenViewSets;
  previousDefinitions: UnifiedFilterDefinition[];
  dataSources: DatasourceItem[];
}): UnifiedFilterDefinition[] => {
  const previousMap = new Map(
    previousDefinitions.map((definition) => [definition.id, definition]),
  );
  const nextDefinitions = new Map<string, UnifiedFilterDefinition>();

  viewSets.items.forEach((item) => {
    const rawId = item.config?.dataSource;
    const dataSourceId =
      typeof rawId === 'string' ? parseInt(rawId, 10) : rawId;
    const dataSource = dataSources.find((source) => source.id === dataSourceId);
    const params = resolveScreenWidgetParams(item, dataSource);
    params?.forEach((param) => {
      if (param.filterType !== 'filter') return;
      if (param.type !== 'string' && param.type !== 'timeRange') return;

      const id = getFilterDefinitionId(param.name, param.type);
      if (nextDefinitions.has(id)) return;

      const existing = previousMap.get(id);
      nextDefinitions.set(id, {
        id,
        key: param.name,
        name: existing?.name || param.alias_name || param.name,
        type: param.type,
        defaultValue:
          existing?.defaultValue ??
          (param.value as UnifiedFilterDefinition['defaultValue']) ??
          null,
        order: existing?.order ?? nextDefinitions.size,
        enabled: existing?.enabled ?? true,
        inputMode: existing?.inputMode,
        options: existing?.options,
      });
    });
  });

  return Array.from(nextDefinitions.values()).sort((a, b) => {
    const orderDiff = (a.order ?? 0) - (b.order ?? 0);
    if (orderDiff !== 0) return orderDiff;
    return a.id.localeCompare(b.id);
  });
};
```

- [ ] **Step 2: Add helper to clean screen widget bindings**

Add:

```ts
export const syncScreenFilterBindings = (
  viewSets: ScreenViewSets,
  definitions: UnifiedFilterDefinition[],
  dataSources: DatasourceItem[],
): ScreenViewSets => ({
  ...viewSets,
  filters: definitions,
  items: viewSets.items.map((item) => {
    const rawId = item.config?.dataSource;
    const dataSourceId =
      typeof rawId === 'string' ? parseInt(rawId, 10) : rawId;
    const dataSource = dataSources.find((source) => source.id === dataSourceId);
    const params = resolveScreenWidgetParams(item, dataSource);
    const nextBindings = buildDefaultFilterBindings(
      params,
      definitions,
      item.config?.filterBindings as FilterBindings | undefined,
    );

    if (
      JSON.stringify(nextBindings ?? {}) ===
      JSON.stringify(item.config?.filterBindings ?? {})
    ) {
      return item;
    }

    return {
      ...item,
      config: {
        ...item.config,
        filterBindings: nextBindings,
      },
    };
  }),
});
```

- [ ] **Step 3: Type-check layout utilities**

Run:

```bash
cd web && pnpm type-check
```

Expected: no new errors in screen layout utilities.

## Task 5: Screen Page Query UI and State

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`

- [ ] **Step 1: Add imports**

Add imports:

```ts
import { Select } from 'antd';
import { UnifiedFilterBar, UnifiedFilterConfigModal } from '@/app/ops-analysis/components/unifiedFilter';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { useOpsAnalysisQueryState } from '@/app/ops-analysis/hooks/useOpsAnalysisQueryState';
import {
  collectScreenDataSourceIds,
  collectScreenNamespaceIds,
} from '@/app/ops-analysis/utils/canvasResources';
import {
  buildFiltersFromScreenItems,
  syncScreenFilterBindings,
} from './utils/layout';
```

Remove `collectScreenDataSourceIds` from the existing `./utils/layout` import in `screen/index.tsx`; this file must import `collectScreenDataSourceIds` from `@/app/ops-analysis/utils/canvasResources`.

- [ ] **Step 2: Initialize query state**

Inside `Screen`, add:

```ts
const { namespaceList } = useOpsAnalysis();
const queryState = useOpsAnalysisQueryState();
const [filterConfigOpen, setFilterConfigOpen] = useState(false);
```

After screen detail load normalizes view sets, initialize query state:

```ts
const normalized = normalizeScreenViewSets(data?.view_sets);
const definitions = normalized.filters ?? [];
queryState.resetQueryState({
  definitions,
  filterValues: {},
  appliedFilterValues: {},
});
```

Also reset query state in fallback and empty-screen branches.

- [ ] **Step 3: Build namespace options**

Add a memo:

```ts
const namespaceOptions = useMemo(() => {
  const namespaceIds = collectScreenNamespaceIds(activeViewSets, dataSources);
  if (namespaceIds.size === 0) return [];
  return namespaceList
    .filter((namespace) => namespaceIds.has(namespace.id))
    .map((namespace) => ({
      label: namespace.name || String(namespace.id),
      value: namespace.id,
    }));
}, [activeViewSets, dataSources, namespaceList]);
```

Add an effect to keep draft/applied namespace valid:

```ts
useEffect(() => {
  if (namespaceOptions.length === 0) {
    queryState.setNamespaceDraftId(undefined);
    queryState.setAppliedNamespaceId(undefined);
    return;
  }
  const hasDraft = namespaceOptions.some(
    (option) => option.value === queryState.namespaceDraftId,
  );
  const fallback = namespaceOptions[0]?.value;
  if (!hasDraft) {
    queryState.setNamespaceDraftId(fallback);
  }
  if (queryState.appliedNamespaceId === undefined) {
    queryState.setAppliedNamespaceId(fallback);
  }
}, [
  namespaceOptions,
  queryState.namespaceDraftId,
  queryState.appliedNamespaceId,
  queryState.setNamespaceDraftId,
  queryState.setAppliedNamespaceId,
]);
```

- [ ] **Step 4: Render the namespace selector**

Add:

```tsx
const namespaceSelectorElement = useMemo(() => {
  if (namespaceOptions.length <= 1) return undefined;
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-(--color-text-2) whitespace-nowrap">
        {t('namespace.title')}:
      </span>
      <Select
        value={queryState.namespaceDraftId}
        onChange={queryState.setNamespaceDraftId}
        options={namespaceOptions}
        style={{ minWidth: 160 }}
      />
    </div>
  );
}, [
  namespaceOptions,
  queryState.namespaceDraftId,
  queryState.setNamespaceDraftId,
  t,
]);
```

- [ ] **Step 5: Render `UnifiedFilterBar` above the screen canvas**

Inside `CanvasWorkspace`, before `{screenCanvas}`, render:

```tsx
{!isFullscreen &&
  (queryState.definitions.length > 0 || namespaceSelectorElement || editMode) && (
    <UnifiedFilterBar
      definitions={queryState.definitions}
      values={queryState.filterValues}
      onChange={queryState.setFilterValues}
      onSearch={(values) =>
        queryState.applyQuery(values, queryState.namespaceDraftId)
      }
      onReset={(values) =>
        queryState.applyQuery(values, queryState.namespaceDraftId)
      }
      prefixContent={namespaceSelectorElement}
    />
  )}
{screenCanvas}
```

- [ ] **Step 6: Add filter config modal**

Add the modal near `ScreenConfigModal`:

```tsx
<UnifiedFilterConfigModal
  open={filterConfigOpen}
  onCancel={() => setFilterConfigOpen(false)}
  onConfirm={(definitions) => {
    const nextViewSets = {
      ...draftViewSets,
      filters: definitions,
    };
    const syncedViewSets = syncScreenFilterBindings(
      nextViewSets,
      definitions,
      dataSources,
    );
    setDraftViewSets(syncedViewSets);
    queryState.setDefinitions(definitions);
    setFilterConfigOpen(false);
  }}
  definitions={queryState.definitions}
  layoutItems={draftViewSets.items.map((item) => ({
    i: item.id,
    x: item.x,
    y: item.y,
    w: item.w,
    h: item.h,
    name: item.title,
    valueConfig: item.config,
  }))}
  dataSources={dataSources}
/>
```

- [ ] **Step 7: Add the filter configuration button to `ScreenToolbar`**

Modify `web/src/app/ops-analysis/(pages)/view/screen/components/screenToolbar.tsx`.

Add the icon import:

```ts
import {
  EditOutlined,
  FilterOutlined,
  FullscreenOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
```

Add the prop:

```ts
onOpenFilterConfig: () => void;
```

Destructure it from props, then render this button in the existing `editMode && (...)` block before the add-widget button:

```tsx
{editMode && (
  <>
    <Button
      type="default"
      icon={<FilterOutlined />}
      className="rounded-full!"
      onClick={onOpenFilterConfig}
    >
      {t('dashboard.unifiedFilterConfig')}
    </Button>
    <Button
      type="default"
      icon={<PlusOutlined />}
      className="rounded-full!"
      onClick={onOpenWidgetSelector}
    >
      {t('opsAnalysis.screen.addWidget')}
    </Button>
  </>
)}
```

In `screen/index.tsx`, pass the handler to `ScreenToolbar`:

```tsx
onOpenFilterConfig={() => setFilterConfigOpen(true)}
```

## Task 6: Screen Save/Cancel and Widget Mutation Sync

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`

- [ ] **Step 1: Sync filters after adding a widget**

In `handleConfirmNewWidgetConfig`, after building the next view sets, rebuild filters:

```ts
setDraftViewSets((current) => {
  const nextViewSets = addConfiguredScreenWidget(current, values);
  const nextDefinitions = buildFiltersFromScreenItems({
    viewSets: nextViewSets,
    previousDefinitions: queryState.definitions,
    dataSources,
  });
  queryState.setDefinitions(nextDefinitions);
  return syncScreenFilterBindings(nextViewSets, nextDefinitions, dataSources);
});
```

- [ ] **Step 2: Sync filters after editing a widget**

In `handleConfirmWidgetConfig`, after `nextItem` is created:

```ts
setDraftViewSets((current) => {
  const nextViewSets = updateScreenItemConfig(
    current,
    currentConfigItem.id,
    nextItem,
  );
  const nextDefinitions = buildFiltersFromScreenItems({
    viewSets: nextViewSets,
    previousDefinitions: queryState.definitions,
    dataSources,
  });
  queryState.setDefinitions(nextDefinitions);
  return syncScreenFilterBindings(nextViewSets, nextDefinitions, dataSources);
});
```

- [ ] **Step 3: Sync filters after deleting a widget**

In `handleDeleteItem`, replace the state update with:

```ts
setDraftViewSets((current) => {
  const nextViewSets = deleteScreenItem(current, itemId);
  const nextDefinitions = buildFiltersFromScreenItems({
    viewSets: nextViewSets,
    previousDefinitions: queryState.definitions,
    dataSources,
  });
  queryState.setDefinitions(nextDefinitions);
  return syncScreenFilterBindings(nextViewSets, nextDefinitions, dataSources);
});
```

- [ ] **Step 4: Reset query state on cancel**

In `handleCancelEdit`, after restoring draft view sets:

```ts
queryState.resetQueryState({
  definitions: savedViewSets.filters ?? [],
  filterValues: queryState.appliedFilterValues,
  appliedFilterValues: queryState.appliedFilterValues,
  namespaceDraftId: queryState.appliedNamespaceId,
  appliedNamespaceId: queryState.appliedNamespaceId,
});
```

- [ ] **Step 5: Persist filters on save**

Before `saveScreen`, create:

```ts
const nextDraftViewSets = {
  ...draftViewSets,
  filters: queryState.definitions,
};
```

Use `nextDraftViewSets` for `view_sets`, `setViewSets`, `setSavedViewSets`, and `setDraftViewSets`.

## Task 7: Pass Query Context to Screen Widgets

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenCanvas.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/components/screenWidgetRenderer.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/index.tsx`

- [ ] **Step 1: Add props to `ScreenCanvas`**

Add imports:

```ts
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
```

Add props:

```ts
filterDefinitions?: UnifiedFilterDefinition[];
unifiedFilterValues?: Record<string, FilterValue>;
filterSearchVersion?: number;
namespaceSearchVersion?: number;
builtinNamespaceId?: number;
```

Pass them to `ScreenWidgetRenderer`.

- [ ] **Step 2: Add props to `ScreenWidgetRenderer`**

Remove `EMPTY_FILTER_VALUES` and `EMPTY_FILTER_DEFINITIONS`.

Add props:

```ts
filterDefinitions?: UnifiedFilterDefinition[];
unifiedFilterValues?: Record<string, FilterValue>;
filterSearchVersion?: number;
namespaceSearchVersion?: number;
builtinNamespaceId?: number;
```

Pass them to `WidgetWrapper`:

```tsx
<WidgetWrapper
  dashboardId={screenId}
  widgetId={item.id}
  chartType={item.chartType}
  config={widgetConfig}
  dataSource={dataSource}
  screenRenderContext={screenRenderContext}
  filterSearchVersion={filterSearchVersion}
  namespaceSearchVersion={namespaceSearchVersion}
  reloadVersion={`screen:${refreshVersion}`}
  unifiedFilterValues={unifiedFilterValues}
  filterDefinitions={filterDefinitions}
  builtinNamespaceId={builtinNamespaceId}
/>
```

- [ ] **Step 3: Pass query context from `Screen`**

For normal and fullscreen `ScreenCanvas`, pass:

```tsx
filterDefinitions={queryState.definitions}
unifiedFilterValues={queryState.appliedFilterValues}
filterSearchVersion={queryState.filterSearchVersion}
namespaceSearchVersion={queryState.namespaceSearchVersion}
builtinNamespaceId={queryState.appliedNamespaceId}
```

- [ ] **Step 4: Pass query context to `ViewConfig`**

For current and pending widget config drawers, pass:

```tsx
builtinNamespaceId={queryState.namespaceDraftId}
filterDefinitions={queryState.definitions}
unifiedFilterValues={queryState.filterValues}
```

## Task 8: Manual Verification

**Files:**
- No code files. Use `/ops-analysis` in the browser.

- [ ] **Step 1: Start the web dev server**

Run:

```bash
cd web && pnpm dev
```

Expected: app is available at `http://localhost:3000`.

- [ ] **Step 2: Open and log in**

Open:

```txt
http://localhost:3000/ops-analysis
```

Login with:

```txt
admin / password
```

- [ ] **Step 3: Verify screen filter bar**

Open a screen containing widgets with data source filter params. Expected:

- normal view shows a filter bar when filters or namespace options exist
- fullscreen hides the filter bar
- search refreshes widgets using applied values
- manual refresh refreshes all widgets

- [ ] **Step 4: Verify edit behavior**

In edit mode:

- open unified filter configuration
- add or confirm generated filters
- bind a widget param to a filter in the component config drawer
- save, reload, and confirm `view_sets.filters` persists
- edit again, change filters, cancel, and confirm the previous saved filters return

- [ ] **Step 5: Run minimal gate**

Run:

```bash
cd web && pnpm type-check
```

Expected: no new errors introduced by the screen unified filter files. If unrelated existing errors remain, list their file paths in the implementation summary.

## Self-Review Notes

- Spec coverage: the plan covers persisted screen filters, page query state, namespace behavior, edit/save/cancel, widget data flow, fullscreen hiding, and manual verification.
- Scope control: dashboard/topology are not deeply migrated; only shared pure utilities may be extracted.
- No placeholders: every task names concrete files and expected code shapes.
