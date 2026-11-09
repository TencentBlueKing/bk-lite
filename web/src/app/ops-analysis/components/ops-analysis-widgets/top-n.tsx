import React, { useEffect } from 'react';
import { resolveOpsChartThemeName } from '@/app/ops-analysis/components/ops-analysis-widgets/runtime';
import type {
  DatasourceItem,
  ResponseFieldDefinition,
  ValueConfig,
} from '@/app/ops-analysis/components/ops-analysis-widgets';
import ChartSurface from '@/components/chart-surface';
import { formatVisibleChartValue } from '@/app/ops-analysis/utils/chartValueFormat';
import {
  buildTopNItems,
  resolveConfiguredTopNBarPercent,
} from '@/app/ops-analysis/utils/topNData';

export interface OpsAnalysisTopNProps {
  rawData: any;
  loading?: boolean;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  onReady?: (ready: boolean) => void;
}

export const resolveTopNHeaderLabel = (fieldKey?: string, fieldSchema?: ResponseFieldDefinition[]) => {
  const key = String(fieldKey || '').trim();
  if (!key) return '';

  const field = (fieldSchema || []).find((item) => item.key === key);
  const title = String(field?.title || '').trim();

  return title ? `${title}（${key}）` : key;
};

const OpsAnalysisTopN: React.FC<OpsAnalysisTopNProps> = ({
  rawData,
  loading = false,
  config,
  dataSource,
  onReady,
}) => {
  const themeName = resolveOpsChartThemeName();
  const isDark = themeName === 'dark';
  const labelField = config?.topNLabelField;
  const valueField = config?.topNValueField;
  const labelHeader = resolveTopNHeaderLabel(labelField, dataSource?.field_schema);
  const valueHeader = resolveTopNHeaderLabel(valueField, dataSource?.field_schema);

  const items = buildTopNItems(rawData, labelField, valueField, {
    scalarFields: config?.topNScalarFields,
  });
  const isDataReady = items.length > 0;

  useEffect(() => {
    if (!loading && onReady) {
      onReady(isDataReady);
    }
  }, [isDataReady, loading, onReady]);

  // 左右约各占一半：左侧列名，右侧进度条+数值；表头固定，仅内容区滚动。
  const columns = 'minmax(0, 1fr) minmax(0, 1fr)';
  const headerColor = isDark ? 'rgba(255,255,255,0.66)' : '#5f6f89';
  const labelColor = isDark ? 'rgba(255,255,255,0.82)' : '#26364f';
  const valueColor = isDark ? 'rgba(255,255,255,0.88)' : '#1f2d44';
  const trackColor = isDark ? 'rgba(255,255,255,0.09)' : '#e8eef8';
  const barGradient = isDark
    ? 'linear-gradient(90deg, #5b8cff 0%, #2f6bff 100%)'
    : 'linear-gradient(90deg, #4f7df3 0%, #235ee8 100%)';

  return (
    <ChartSurface
      loading={loading}
      hasData={isDataReady}
      containerClassName="flex h-full flex-col overflow-hidden px-3 pt-2 pb-1"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="flex h-full w-full items-center justify-center"
    >
      {(labelHeader || valueHeader) && (
        <div
          className="mb-1.5 grid shrink-0 items-center rounded-md py-0.5 text-[12px] font-medium"
          style={{
            gridTemplateColumns: columns,
            columnGap: 8,
            color: headerColor,
          }}
        >
          <span className="min-w-0 truncate px-2" title={labelHeader}>
            {labelHeader}
          </span>
          <span className="min-w-0 truncate text-right px-2" title={valueHeader}>
            {valueHeader}
          </span>
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div
          className="grid items-center"
          style={{
            gridTemplateColumns: columns,
            columnGap: 8,
            rowGap: 2,
          }}
        >
          {items.map((item, index) => {
            const percent = resolveConfiguredTopNBarPercent(item.value, items, config);

            return (
              <React.Fragment key={`${item.name}-${index}`}>
                <span
                  className="flex h-7 min-w-0 items-center truncate rounded-l-md px-2 text-[13px]"
                  style={{ color: labelColor }}
                  title={item.name}
                >
                  {item.name}
                </span>
                <div className="flex h-7 min-w-0 items-center gap-2 rounded-r-md pr-2">
                  <div
                    className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full"
                    style={{ backgroundColor: trackColor }}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{
                        width: `${percent}%`,
                        background: barGradient,
                      }}
                    />
                  </div>
                  <span
                    className="shrink-0 min-w-[48px] text-right text-[13px] font-semibold tabular-nums"
                    style={{ color: valueColor }}
                  >
                    {formatVisibleChartValue(item.value, config)}
                  </span>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </ChartSurface>
  );
};

export default OpsAnalysisTopN;
