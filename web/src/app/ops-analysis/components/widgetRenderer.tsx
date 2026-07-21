import React from 'react';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  ScreenRenderContext,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import { getWidgetComponent } from './widgetRegistry';

interface WidgetRendererProps {
  chartType?: string;
  rawData: any;
  baselineData?: any;
  loading?: boolean;
  config?: ValueConfig;
  refreshKey?: string | number;
  dataSource?: DatasourceItem;
  screenRenderContext?: ScreenRenderContext;
  onReady?: (ready?: boolean) => void;
  onQueryChange?: (params: Record<string, any>) => void;
  componentSwitchControl?: React.ReactNode;
  errorMessage?: string;
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
  screenRenderContext,
  onReady,
  onQueryChange,
  componentSwitchControl,
  errorMessage,
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
      screenRenderContext={screenRenderContext}
      onReady={onReady}
      onQueryChange={onQueryChange}
      {...(chartType === 'topN' ? { componentSwitchControl, errorMessage } : {})}
    />
  );
};

export default WidgetRenderer;
