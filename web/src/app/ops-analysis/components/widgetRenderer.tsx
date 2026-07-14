import React from 'react';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  RuntimeParamValue,
  ScreenRenderContext,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import { getWidgetComponent } from './widgetRegistry';
import { buildWidgetRuntimeInteractionProps } from '@/app/ops-analysis/utils/runtimeParamControl';

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
  runtimeParamValue?: RuntimeParamValue;
  onRuntimeParamChange?: (value: RuntimeParamValue) => void;
  runtimeParamControlPlacement?: 'header' | 'inline';
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
  runtimeParamValue,
  onRuntimeParamChange,
  runtimeParamControlPlacement,
  errorMessage,
  fallback = null,
}) => {
  const Component = getWidgetComponent(chartType);
  if (!Component) {
    return <>{fallback}</>;
  }

  const runtimeInteractionProps = buildWidgetRuntimeInteractionProps(
    chartType,
    {
      runtimeParamValue,
      onRuntimeParamChange,
      errorMessage,
    },
  );

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
      {...runtimeInteractionProps}
      {...(chartType === 'topN' ? { runtimeParamControlPlacement } : {})}
    />
  );
};

export default WidgetRenderer;
