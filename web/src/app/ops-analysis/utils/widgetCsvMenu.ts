import {
  resolveAnalysisCanvasInteraction,
  shouldShowAnalysisWidgetCopyAction,
} from '@/app/ops-analysis/utils/widgetCopy';
import { isWidgetCsvExportDataBlocked, supportsWidgetCsvExport } from '@/app/ops-analysis/utils/widgetCsvExport';

export type DashboardWidgetMenuKey = 'edit' | 'copy' | 'delete' | 'exportCsv';

export type WidgetCsvExportSurface = 'dashboard' | 'screen' | 'topology' | 'report';

export type WidgetCsvExportEntry = 'hover' | 'menu' | 'none';

export const isWidgetCsvExportBlocked = ({
  shareMode = false,
  fullscreen = false,
  renderMode = false,
}: {
  shareMode?: boolean;
  fullscreen?: boolean;
  renderMode?: boolean;
}): boolean => Boolean(shareMode || fullscreen || renderMode);

/**
 * 仪表盘、报表、拓扑查看态把图标放进标题栏；编辑态放进已有菜单。
 * 大屏查看态没有入口。分享、全屏、订阅截图和打印准备都不出现入口。
 */
export const resolveWidgetCsvExportEntry = ({
  surface,
  chartType,
  editMode = false,
  shareMode = false,
  fullscreen = false,
  renderMode = false,
  rawData,
}: {
  surface: WidgetCsvExportSurface;
  chartType?: string;
  editMode?: boolean;
  shareMode?: boolean;
  fullscreen?: boolean;
  renderMode?: boolean;
  rawData?: unknown;
}): WidgetCsvExportEntry => {
  if (isWidgetCsvExportBlocked({ shareMode, fullscreen, renderMode })) return 'none';
  if (!supportsWidgetCsvExport(chartType)) return 'none';
  if (isWidgetCsvExportDataBlocked(chartType, rawData)) return 'none';
  if (surface === 'screen') return editMode ? 'menu' : 'none';
  return editMode ? 'menu' : 'hover';
};

export const resolveTopologyCsvExportHoverEnabled = ({
  editMode = false,
  shareMode = false,
  fullscreen = false,
}: {
  editMode?: boolean;
  shareMode?: boolean;
  fullscreen?: boolean;
}): boolean => !editMode && !isWidgetCsvExportBlocked({ shareMode, fullscreen });

export const buildDashboardWidgetMenuKeys = ({
  surface,
  isEditMode,
  shareMode = false,
  isBuiltIn = false,
  renderMode = false,
  fullscreen = false,
  chartType,
  sceneWidgetType,
  rawData,
}: {
  surface: WidgetCsvExportSurface;
  isEditMode: boolean;
  shareMode?: boolean;
  isBuiltIn?: boolean;
  renderMode?: boolean;
  fullscreen?: boolean;
  chartType?: string;
  sceneWidgetType?: string;
  rawData?: unknown;
}): DashboardWidgetMenuKey[] => {
  const keys: DashboardWidgetMenuKey[] = [];
  const exportCsv = resolveWidgetCsvExportEntry({
    surface,
    chartType,
    editMode: isEditMode,
    shareMode,
    fullscreen,
    renderMode,
    rawData,
  }) === 'menu';
  if (isEditMode) {
    keys.push('edit');
    if (shouldShowAnalysisWidgetCopyAction({
      interaction: resolveAnalysisCanvasInteraction({
        editMode: isEditMode,
        shareMode,
        isBuiltIn,
      }),
      sceneWidgetType,
      chartType,
    })) {
      keys.push('copy');
    }
    if (exportCsv) keys.push('exportCsv');
    keys.push('delete');
    return keys;
  }
  return keys;
};

export interface AnalysisWidgetMenuItem {
  key: DashboardWidgetMenuKey;
  label: string;
  danger?: boolean;
  onClick: () => void;
}

export const buildAnalysisWidgetMenuItems = ({
  keys,
  t,
  onEdit,
  onCopy,
  onDelete,
  onExportCsv,
}: {
  keys: DashboardWidgetMenuKey[];
  t: (id: string) => string;
  onEdit: () => void;
  onCopy?: () => void;
  onDelete: () => void;
  onExportCsv: () => void;
}): AnalysisWidgetMenuItem[] => keys.map((key) => {
  if (key === 'edit') {
    return { key, label: t('common.edit'), onClick: onEdit };
  }
  if (key === 'copy') {
    return { key, label: t('common.copy'), onClick: () => onCopy?.() };
  }
  if (key === 'exportCsv') {
    return { key, label: t('dashboard.exportCsv'), onClick: onExportCsv };
  }
  return {
    key,
    label: t('common.delete'),
    danger: true,
    onClick: onDelete,
  };
});

export const resolveScreenItemMenuMode = ({
  editMode,
  shareMode = false,
  fullscreen = false,
}: {
  editMode: boolean;
  shareMode?: boolean;
  fullscreen?: boolean;
}): 'edit' | 'view' => (
  editMode && !shareMode && !fullscreen ? 'edit' : 'view'
);
