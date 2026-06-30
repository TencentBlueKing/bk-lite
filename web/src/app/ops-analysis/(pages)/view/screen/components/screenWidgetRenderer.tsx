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
  dataSourceResolver: (
    dataSource?: string | number,
  ) => DatasourceItem | undefined;
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
  const widgetConfig = useMemo(() => buildScreenWidgetConfig(item), [item]);
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
