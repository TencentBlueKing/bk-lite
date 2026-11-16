import React from 'react';
import type { DatasourceItem, ValueConfig } from '@/app/ops-analysis/components/ops-analysis-widgets';
import { getOpsAnalysisWidgetComponent } from './widget-registry';

export interface OpsAnalysisWidgetRendererProps {
  chartType?: string;
  rawData: any;
  baselineData?: any;
  loading?: boolean;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  onReady?: (ready?: boolean) => void;
  onQueryChange?: (params: Record<string, any>) => void;
  fallback?: React.ReactNode;
}

const OpsAnalysisWidgetRenderer: React.FC<OpsAnalysisWidgetRendererProps> = ({
  chartType,
  rawData,
  baselineData,
  loading = false,
  config,
  dataSource,
  onReady,
  onQueryChange,
  fallback = null,
}) => {
  const Component = getOpsAnalysisWidgetComponent(chartType);
  if (!Component) {
    return <>{fallback}</>;
  }

  return (
    <Component
      rawData={rawData}
      baselineData={baselineData}
      loading={loading}
      config={config}
      dataSource={dataSource}
      onReady={onReady}
      onQueryChange={onQueryChange}
    />
  );
};

export default OpsAnalysisWidgetRenderer;
