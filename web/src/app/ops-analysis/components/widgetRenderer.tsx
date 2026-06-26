import React from 'react';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import { getWidgetComponent } from './widgetRegistry';

interface WidgetRendererProps {
  chartType?: string;
  rawData: any;
  baselineData?: any;
  loading?: boolean;
  config?: ValueConfig;
  refreshKey?: string | number;
  dataSource?: DatasourceItem;
  onReady?: (ready?: boolean) => void;
  onQueryChange?: (params: Record<string, any>) => void;
  fallback?: React.ReactNode;
}

const WidgetRenderer: React.FC<WidgetRendererProps> = ({
  chartType,
  rawData,
  baselineData,
  loading = false,
  config,
  refreshKey,
  dataSource,
  onReady,
  onQueryChange,
  fallback = null,
}) => {
  const Component = getWidgetComponent(chartType);
  if (!Component) {
    return <>{fallback}</>;
  }

  return (
    <Component
      rawData={rawData}
      baselineData={baselineData}
      loading={loading}
      config={config}
      refreshKey={refreshKey}
      dataSource={dataSource}
      onReady={onReady}
      onQueryChange={onQueryChange}
    />
  );
};

export default WidgetRenderer;
