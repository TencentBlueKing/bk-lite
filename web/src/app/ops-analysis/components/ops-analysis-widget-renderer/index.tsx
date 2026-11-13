import React from 'react';
import type { DatasourceItem, ValueConfig } from '@/app/ops-analysis/components/ops-analysis-widgets';
import { genericStructureMismatch } from '@/app/ops-analysis/utils/genericStructure';
import { useTranslation } from '@/utils/i18n';
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
  const { t } = useTranslation();
  const mismatch = genericStructureMismatch(rawData, chartType);
  const Component = getOpsAnalysisWidgetComponent(chartType);
  if (mismatch) {
    return (
      <div data-testid="structure-mismatch">
        {t(
          'dashboard.structureMismatch',
          '当前结果结构是 {current}，这个图表需要 {required}。请修改分析方式或更换图表。',
          {
            current: t(`dashboard.structureName.${mismatch.current}`, mismatch.current),
            required: t(`dashboard.structureName.${mismatch.required}`, mismatch.required),
          },
        )}
      </div>
    );
  }
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
