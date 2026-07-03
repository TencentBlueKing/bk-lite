'use client';

import React, { useMemo } from 'react';
import WidgetWrapper from '@/app/ops-analysis/components/widgetDataRenderer';
import type { FilterValue, UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import { buildScreenWidgetConfig } from '../utils/widgetConfig';
import ScreenWidgetFrame from './screenWidgetFrame';

interface ScreenWidgetRendererProps {
  item: ScreenWidgetItem;
  selected?: boolean;
  editMode?: boolean;
  refreshVersion: number;
  screenId?: string | number;
  fitScale: number;
  screenDensity: number;
  screenUiScale: number;
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, FilterValue>;
  filterSearchVersion?: number;
  namespaceSearchVersion?: number;
  builtinNamespaceId?: number;
  dataSourceResolver: (
    dataSource?: string | number,
  ) => DatasourceItem | undefined;
  onEditConfig?: (item: ScreenWidgetItem) => void;
  onDelete?: (itemId: string) => void;
}

const ScreenWidgetRenderer: React.FC<ScreenWidgetRendererProps> = ({
  item,
  selected = false,
  editMode = false,
  refreshVersion,
  screenId,
  fitScale,
  screenDensity,
  screenUiScale,
  filterDefinitions,
  unifiedFilterValues,
  filterSearchVersion = 0,
  namespaceSearchVersion = 0,
  builtinNamespaceId,
  dataSourceResolver,
  onEditConfig,
  onDelete,
}) => {
  const widgetConfig = useMemo(() => buildScreenWidgetConfig(item), [item]);
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
    </ScreenWidgetFrame>
  );
};

export default ScreenWidgetRenderer;
