import { v4 as uuidv4 } from 'uuid';
import type {
  DashboardLayoutItem,
  DashboardWidgetLayoutItem,
  ValueConfig,
  WidgetConfig,
} from '@/app/ops-analysis/types/dashBoard';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
import type { ReportViewSets } from '@/app/ops-analysis/types/report';
import { isSceneWidgetType } from '@/app/ops-analysis/types/sceneWidgetCapability';
import {
  insertDashboardWidgetIntoGroup,
  isDashboardGroupItem,
  isDashboardWidgetItem,
} from '@/app/ops-analysis/utils/dashboardGroups';

const RUNTIME_VALUE_CONFIG_KEYS = ['rawData', 'loading', 'scheduler'] as const;

export type AnalysisCanvasInteraction = 'edit' | 'view' | 'share' | 'builtin';

export interface AnalysisWidgetCloneSource {
  id: string;
  title?: string | null;
  valueConfig?: ValueConfig & { name?: string };
}

export interface AnalysisWidgetCloneResult {
  id: string;
  title: string;
  valueConfig: ValueConfig & { name?: string };
}

const cloneJson = <T,>(value: T): T => {
  if (value === undefined) {
    return value;
  }
  return JSON.parse(JSON.stringify(value)) as T;
};

export const cloneCopiedWidgetTitle = (name?: string | null): string => {
  const trimmed = name?.trim() ?? '';
  return trimmed ? `${trimmed} 副本` : '副本';
};

export const cloneAnalysisWidgetValueConfig = <T extends ValueConfig>(
  valueConfig?: T,
): T => {
  const cloned = cloneJson((valueConfig ?? {}) as T & Record<string, unknown>);
  RUNTIME_VALUE_CONFIG_KEYS.forEach((key) => {
    delete cloned[key];
  });
  return cloned;
};

export const isCopyableAnalysisWidget = (input?: {
  sceneWidgetType?: string;
  chartType?: string;
}): boolean =>
  !isSceneWidgetType(input?.sceneWidgetType) && !isSceneWidgetType(input?.chartType);

export const shouldShowAnalysisWidgetCopyAction = (input: {
  interaction: AnalysisCanvasInteraction;
  sceneWidgetType?: string;
  chartType?: string;
}): boolean =>
  input.interaction === 'edit' && isCopyableAnalysisWidget(input);

export const cloneAnalysisWidget = (
  source: AnalysisWidgetCloneSource,
  options?: { createId?: () => string },
): AnalysisWidgetCloneResult => {
  const createId = options?.createId ?? uuidv4;
  const sourceName =
    source.title ??
    (typeof source.valueConfig?.name === 'string' ? source.valueConfig.name : '');
  const title = cloneCopiedWidgetTitle(sourceName);
  const valueConfig = cloneAnalysisWidgetValueConfig(source.valueConfig);
  if (source.valueConfig && 'name' in source.valueConfig) {
    (valueConfig as WidgetConfig).name = title;
  }
  return {
    id: createId(),
    title,
    valueConfig,
  };
};

const DASHBOARD_GRID_COLS = 12;

const boxesOverlap = (
  left: { x: number; y: number; w: number; h: number },
  right: { x: number; y: number; w: number; h: number },
) =>
  !(
    left.x + left.w <= right.x ||
    right.x + right.w <= left.x ||
    left.y + left.h <= right.y ||
    right.y + right.h <= left.y
  );

const canPlaceDashboardWidgetAt = (
  x: number,
  y: number,
  widget: Pick<DashboardWidgetLayoutItem, 'w' | 'h'>,
  blockers: Array<{ x: number; y: number; w: number; h: number }>,
  cols: number,
) => {
  if (x < 0 || y < 0 || x + widget.w > cols) {
    return false;
  }
  return blockers.every((item) => !boxesOverlap({ x, y, w: widget.w, h: widget.h }, item));
};

export const copyDashboardWidget = (
  layout: DashboardLayoutItem[],
  sourceId: string,
  options?: { createId?: () => string },
): DashboardLayoutItem[] => {
  const source = layout.find((item) => item.i === sourceId);
  if (
    !source ||
    !isDashboardWidgetItem(source) ||
    !isCopyableAnalysisWidget(source.valueConfig)
  ) {
    return layout;
  }

  const clonedMeta = cloneAnalysisWidget(
    {
      id: source.i,
      title: source.name,
      valueConfig: source.valueConfig,
    },
    options,
  );
  const cloned: DashboardWidgetLayoutItem = {
    ...source,
    i: clonedMeta.id,
    name: clonedMeta.title,
    valueConfig: clonedMeta.valueConfig,
    groupId: source.groupId ?? null,
  };
  const preferredX = source.x + 1;
  const preferredY = source.y;

  if (cloned.groupId) {
    const group = layout.find(
      (item) => item.i === cloned.groupId && isDashboardGroupItem(item),
    );
    const blockers = layout.filter(
      (item): item is DashboardWidgetLayoutItem =>
        isDashboardWidgetItem(item) && item.groupId === cloned.groupId,
    );
    const cols = group ? group.w : DASHBOARD_GRID_COLS;
    if (canPlaceDashboardWidgetAt(preferredX, preferredY, cloned, blockers, cols)) {
      return [
        ...layout,
        {
          ...cloned,
          x: preferredX,
          y: preferredY,
          groupId: cloned.groupId,
        },
      ];
    }
    if (group) {
      return insertDashboardWidgetIntoGroup(layout, cloned, cloned.groupId);
    }
  }

  const blockers = layout;
  if (
    canPlaceDashboardWidgetAt(
      preferredX,
      preferredY,
      cloned,
      blockers,
      DASHBOARD_GRID_COLS,
    )
  ) {
    return [...layout, { ...cloned, x: preferredX, y: preferredY }];
  }

  const maxY = Math.max(0, ...layout.map((item) => item.y + item.h));
  for (let y = 0; y <= maxY + cloned.h; y += 1) {
    for (let x = 0; x <= DASHBOARD_GRID_COLS - cloned.w; x += 1) {
      if (canPlaceDashboardWidgetAt(x, y, cloned, blockers, DASHBOARD_GRID_COLS)) {
        return [...layout, { ...cloned, x, y }];
      }
    }
  }
  return [...layout, { ...cloned, x: 0, y: maxY }];
};

const SCREEN_COPY_OFFSET = 48;

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

export const copyScreenWidget = (
  viewSets: ScreenViewSets,
  sourceId: string,
  options?: { createId?: () => string },
): { viewSets: ScreenViewSets; selectedItemId: string } | null => {
  const source = viewSets.items.find((item) => item.id === sourceId);
  if (
    !source ||
    !isCopyableAnalysisWidget({
      sceneWidgetType: source.valueConfig?.sceneWidgetType,
      chartType: source.chartType,
    })
  ) {
    return null;
  }

  const clonedMeta = cloneAnalysisWidget(
    {
      id: source.id,
      title: source.title,
      valueConfig: source.valueConfig,
    },
    options,
  );
  const maxZ = viewSets.items.reduce(
    (max, item) => Math.max(max, item.zIndex || 0),
    0,
  );
  const copied = {
    ...source,
    id: clonedMeta.id,
    title: clonedMeta.title,
    valueConfig: clonedMeta.valueConfig,
    x: clamp(
      source.x + SCREEN_COPY_OFFSET,
      0,
      Math.max(0, viewSets.viewport.width - source.w),
    ),
    y: clamp(
      source.y + SCREEN_COPY_OFFSET,
      0,
      Math.max(0, viewSets.viewport.height - source.h),
    ),
    zIndex: maxZ + 1,
  };

  return {
    viewSets: {
      ...viewSets,
      items: [...viewSets.items, copied],
    },
    selectedItemId: copied.id,
  };
};

export const copyReportSection = (
  viewSets: ReportViewSets,
  sourceId: string,
  options?: { createId?: () => string },
): ReportViewSets => {
  const sourceIndex = viewSets.sections.findIndex(
    (section) => section.id === sourceId,
  );
  const source = viewSets.sections[sourceIndex];
  if (
    !source ||
    !isCopyableAnalysisWidget({
      sceneWidgetType: source.valueConfig.sceneWidgetType,
      chartType: source.valueConfig.chartType,
    })
  ) {
    return viewSets;
  }

  const clonedMeta = cloneAnalysisWidget(
    {
      id: source.id,
      title: source.valueConfig.name,
      valueConfig: source.valueConfig,
    },
    options,
  );
  const copied = {
    id: clonedMeta.id,
    valueConfig: {
      ...clonedMeta.valueConfig,
      name: clonedMeta.title,
    },
  };
  const sections = [...viewSets.sections];
  sections.splice(sourceIndex + 1, 0, copied);
  return {
    ...viewSets,
    sections,
  };
};

