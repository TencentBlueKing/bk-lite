'use client';

import React, { useMemo } from 'react';
import WidgetWrapper from '@/app/ops-analysis/components/widgetDataRenderer';
import type { FilterValue, UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import type { DashboardWidgetRenderResult } from '@/app/ops-analysis/renderContract';
import type { CanvasRuntimeRefreshCause } from '@/app/ops-analysis/utils/canvasRefreshTimer';
import { buildScreenWidgetConfig } from '../utils/widgetConfig';
import ScreenWidgetFrame from './screenWidgetFrame';
import { WidgetViewportProvider } from '@/app/ops-analysis/components/widget-viewport';

interface ScreenWidgetRendererProps {
  item: ScreenWidgetItem;
  selected?: boolean;
  editMode?: boolean;
  refreshVersion: number;
  refreshCause?: CanvasRuntimeRefreshCause;
  screenId?: string | number;
  fitScale: number;
  screenDensity: number;
  screenUiScale: number;
  chartThemeMode: OpsChartThemeMode;
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, FilterValue>;
  filterSearchVersion?: number;
  namespaceSearchVersion?: number;
  builtinNamespaceId?: number;
  dataSourceResolver: (
    dataSource?: string | number,
  ) => DatasourceItem | undefined;
  onRenderStatus?: (result: DashboardWidgetRenderResult) => void;
  onEditConfig?: (item: ScreenWidgetItem) => void;
  onDelete?: (itemId: string) => void;
  layoutEditable?: boolean;
  onTopologyLayoutChange?: (
    next: NonNullable<
      NonNullable<ScreenWidgetItem['valueConfig']>['networkStatusTopology']
    >,
  ) => void;
}

const ScreenWidgetRenderer: React.FC<ScreenWidgetRendererProps> = ({
  item,
  selected = false,
  editMode = false,
  refreshVersion,
  refreshCause = 'manual',
  screenId,
  fitScale,
  screenDensity,
  screenUiScale,
  chartThemeMode,
  filterDefinitions,
  unifiedFilterValues,
  filterSearchVersion = 0,
  namespaceSearchVersion = 0,
  builtinNamespaceId,
  dataSourceResolver,
  onRenderStatus,
  onEditConfig,
  onDelete,
  layoutEditable,
  onTopologyLayoutChange,
}) => {
  const widgetConfig = useMemo(
    () => buildScreenWidgetConfig(item, chartThemeMode),
    [chartThemeMode, item],
  );
  const screenRenderContext = useMemo(
    () => ({
      enabled: true,
      fitScale,
      screenDensity,
      screenUiScale,
      widgetDensity: screenDensity,
      widgetUiScale: screenUiScale,
    }),
    [fitScale, screenDensity, screenUiScale],
  );
  const dataSource = dataSourceResolver(widgetConfig.dataSource);

  return (
    <WidgetViewportProvider scale={fitScale}>
      <ScreenWidgetFrame
        item={item}
        selected={selected}
        editMode={editMode}
        screenDensity={screenDensity}
        screenUiScale={screenUiScale}
        onConfigure={() => onEditConfig?.(item)}
        onDelete={() => onDelete?.(item.id)}
      >
        <WidgetWrapper
          dashboardId={screenId}
          widgetId={item.id}
          surface="screen"
          chartType={item.chartType}
          config={widgetConfig}
          dataSource={dataSource}
          screenRenderContext={screenRenderContext}
          filterSearchVersion={filterSearchVersion}
          namespaceSearchVersion={namespaceSearchVersion}
          reloadVersion={`screen:${refreshVersion}`}
          refreshCause={refreshCause}
          unifiedFilterValues={unifiedFilterValues}
          filterDefinitions={filterDefinitions}
          builtinNamespaceId={builtinNamespaceId}
          onRenderStatus={onRenderStatus}
          layoutEditable={layoutEditable}
          onTopologyLayoutChange={onTopologyLayoutChange}
        />
      </ScreenWidgetFrame>
    </WidgetViewportProvider>
  );
};

export default ScreenWidgetRenderer;
