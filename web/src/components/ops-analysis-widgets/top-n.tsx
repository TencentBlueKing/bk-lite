import React, { useEffect } from 'react';
import { getValueByPath } from '@/components/ops-analysis-config-sections';
import { resolveOpsChartThemeName } from '@/components/ops-analysis-widgets/runtime';
import type {
  DatasourceItem,
  ResponseFieldDefinition,
  ValueConfig,
} from '@/components/ops-analysis-widgets';
import ChartSurface from '@/components/chart-surface';

export interface OpsAnalysisTopNProps {
  rawData: any;
  loading?: boolean;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  onReady?: (ready: boolean) => void;
}

interface TopNItem {
  name: string;
  value: number;
}

const unwrapTopNData = (data: any): any[] => {
  if (Array.isArray(data)) {
    return data;
  }

  if (data && typeof data === 'object') {
    if (Array.isArray(data.items)) {
      return data.items;
    }
    if (Array.isArray(data.data)) {
      return data.data;
    }
  }

  return [];
};

export const resolveTopNHeaderLabel = (fieldKey?: string, fieldSchema?: ResponseFieldDefinition[]) => {
  const key = String(fieldKey || '').trim();
  if (!key) return '';

  const field = (fieldSchema || []).find((item) => item.key === key);
  const title = String(field?.title || '').trim();

  return title ? `${key}（${title}）` : key;
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

  const transformData = (data: any): TopNItem[] => {
    const rows = unwrapTopNData(data);
    if (rows.length === 0) return [];

    if (Array.isArray(rows[0])) {
      return rows
        .map((item: any[]) => {
          const rawName = getValueByPath(item, labelField);
          const rawValue = getValueByPath(item, valueField);

          const name = rawName === undefined || rawName === null ? '' : String(rawName).trim();
          const value = Number(rawValue);
          if (!name || Number.isNaN(value)) {
            return null;
          }

          return { name, value };
        })
        .filter((item: TopNItem | null): item is TopNItem => item !== null);
    }

    if (typeof rows[0] === 'object') {
      return rows
        .map((item: any) => {
          const rawName = getValueByPath(item, labelField);
          const rawValue = getValueByPath(item, valueField);

          const name = rawName === undefined || rawName === null ? '' : String(rawName).trim();
          const value = Number(rawValue);
          if (!name || Number.isNaN(value)) {
            return null;
          }

          return { name, value };
        })
        .filter((item: TopNItem | null): item is TopNItem => item !== null);
    }

    return [];
  };

  const items = transformData(rawData);
  const maxValue = items.length > 0 ? Math.max(...items.map((item) => item.value)) : 0;
  const isDataReady = items.length > 0;

  useEffect(() => {
    if (!loading && onReady) {
      onReady(isDataReady);
    }
  }, [isDataReady, loading, onReady]);

  return (
    <ChartSurface
      loading={loading}
      hasData={isDataReady}
      containerClassName="h-full overflow-y-auto px-3 pt-2 pb-1"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="flex h-full w-full items-center justify-center"
    >
      {(labelHeader || valueHeader) && (
        <div
          className="mb-1.5 grid items-center rounded-md py-1.5 text-[12px] font-medium"
          style={{
            gridTemplateColumns: 'minmax(112px, 28%) minmax(0, 1fr) minmax(48px, auto)',
            columnGap: 12,
            color: isDark ? 'rgba(255,255,255,0.66)' : '#5f6f89',
          }}
        >
          <span className="truncate" title={labelHeader}>
            {labelHeader}
          </span>
          <span />
          <span className="truncate text-right" title={valueHeader}>
            {valueHeader}
          </span>
        </div>
      )}
      <div
        className="grid items-center"
        style={{
          gridTemplateColumns: 'minmax(112px, 28%) minmax(0, 1fr) minmax(48px, auto)',
          columnGap: 12,
          rowGap: 2,
        }}
      >
        {items.map((item, index) => {
          const percent = maxValue > 0 ? (item.value / maxValue) * 100 : 0;

          return (
            <React.Fragment key={`${item.name}-${index}`}>
              <span
                className="flex h-7 min-w-0 items-center truncate rounded-l-md px-2 text-[13px]"
                style={{
                  color: isDark ? 'rgba(255,255,255,0.82)' : '#26364f',
                }}
                title={item.name}
              >
                {item.name}
              </span>
              <div className="flex h-7 min-w-0 items-center">
                <div
                  className="h-2.5 w-full overflow-hidden rounded-full"
                  style={{
                    backgroundColor: isDark ? 'rgba(255,255,255,0.09)' : '#e8eef8',
                  }}
                >
                  <div
                    className="h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.max(percent, item.value > 0 ? 2 : 0)}%`,
                      background: isDark
                        ? 'linear-gradient(90deg, #5b8cff 0%, #2f6bff 100%)'
                        : 'linear-gradient(90deg, #4f7df3 0%, #235ee8 100%)',
                    }}
                  />
                </div>
              </div>
              <span
                className="flex h-7 min-w-[48px] items-center justify-end rounded-r-md px-2 text-[13px] font-semibold tabular-nums"
                style={{
                  color: isDark ? 'rgba(255,255,255,0.88)' : '#1f2d44',
                }}
              >
                {item.value.toLocaleString()}
              </span>
            </React.Fragment>
          );
        })}
      </div>
    </ChartSurface>
  );
};

export default OpsAnalysisTopN;
