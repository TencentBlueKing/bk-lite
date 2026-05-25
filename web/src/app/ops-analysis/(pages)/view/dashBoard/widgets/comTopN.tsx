import React, { useEffect } from 'react';
import { Spin, Empty } from 'antd';
import { resolveOpsChartThemeName } from '@/app/ops-analysis/utils/chartTheme';
import { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';

interface TopNProps {
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

const getFallbackLabel = (item: Record<string, any>) => {
  const preferredKeys = ['name', 'label', 'title', 'model', 'model_name', 'model_id', 'id'];

  for (const key of preferredKeys) {
    const value = item[key];
    if (value !== undefined && value !== null && String(value).trim()) {
      return String(value).trim();
    }
  }

  for (const value of Object.values(item)) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }

  return '';
};

const getFallbackValue = (item: Record<string, any>) => {
  const preferredKeys = ['value', 'count', 'total', 'num', 'amount', 'metric', 'size'];

  for (const key of preferredKeys) {
    const value = Number(item[key]);
    if (!Number.isNaN(value)) {
      return value;
    }
  }

  for (const rawValue of Object.values(item)) {
    const value = Number(rawValue);
    if (!Number.isNaN(value)) {
      return value;
    }
  }

  return NaN;
};

const isUsableLabel = (value: unknown) => {
  return value !== undefined && value !== null && String(value).trim() !== '';
};

const isUsableValue = (value: unknown) => {
  return !Number.isNaN(Number(value));
};

const TopN: React.FC<TopNProps> = ({
  rawData,
  loading = false,
  config,
  dataSource,
  onReady,
}) => {
  const themeName = resolveOpsChartThemeName();
  const isDark = themeName === 'dark';

  const inferredLabelField = dataSource?.field_schema?.find(
    (field) => field.value_type !== 'number',
  )?.key;
  const inferredValueField = dataSource?.field_schema?.find(
    (field) => field.value_type === 'number',
  )?.key;

  const transformData = (data: any): TopNItem[] => {
    const rows = unwrapTopNData(data);
    if (rows.length === 0) return [];

    // [[name, value], ...] format
    if (Array.isArray(rows[0])) {
      return rows.map((item: any[]) => ({
        name: String(item[0] ?? ''),
        value: Number(item[1]) || 0,
      }));
    }

    // [{name, value}] format
    if (typeof rows[0] === 'object') {
      return rows
        .map((item: any) => {
          const explicitName = config?.topNLabelField
            ? getValueByPath(item, config.topNLabelField)
            : undefined;
          const explicitValue = config?.topNValueField
            ? getValueByPath(item, config.topNValueField)
            : undefined;

          const inferredName = inferredLabelField
            ? getValueByPath(item, inferredLabelField)
            : undefined;
          const inferredValue = inferredValueField
            ? getValueByPath(item, inferredValueField)
            : undefined;

          const rawName = isUsableLabel(explicitName)
            ? explicitName
            : isUsableLabel(item.name)
              ? item.name
              : isUsableLabel(item.label)
                ? item.label
                : isUsableLabel(inferredName)
                  ? inferredName
                  : getFallbackLabel(item);
          const rawValue = isUsableValue(explicitValue)
            ? explicitValue
            : isUsableValue(item.value)
              ? item.value
              : isUsableValue(item.count)
                ? item.count
                : isUsableValue(inferredValue)
                  ? inferredValue
                  : getFallbackValue(item);

          const name = rawName === undefined || rawName === null ? '' : String(rawName).trim();
          const value = Number(rawValue);
          if (!name || Number.isNaN(value)) {
            return null;
          }

          return {
            name,
            value,
          };
        })
        .filter((item: TopNItem | null): item is TopNItem => item !== null);
    }

    return [];
  };

  const items = transformData(rawData);
  const maxValue = items.length > 0 ? Math.max(...items.map((i) => i.value)) : 0;
  const isDataReady = items.length > 0;

  useEffect(() => {
    if (!loading && onReady) {
      onReady(isDataReady);
    }
  }, [isDataReady, loading, onReady]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!isDataReady) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div className="h-full px-3 pt-2 pb-1 overflow-y-auto">
      <div
        className="grid items-center gap-x-2"
        style={{
          gridTemplateColumns: 'fit-content(40%) minmax(0, 1fr) auto',
          rowGap: 8,
        }}
      >
        {items.map((item, index) => {
          const percent = maxValue > 0 ? (item.value / maxValue) * 100 : 0;

          return (
            <React.Fragment key={`${item.name}-${index}`}>
              <span
                className="text-[13px] truncate"
                style={{
                  color: isDark ? 'var(--color-text-2)' : '#1f2329',
                  minWidth: 0,
                }}
                title={item.name}
              >
                {item.name}
              </span>
              <div className="flex items-center h-[30px] min-w-0">
                <div
                  className="h-3 rounded-sm transition-all duration-300"
                  style={{
                    width: `${Math.max(percent, 1.5)}%`,
                    backgroundColor: '#366CE4',
                  }}
                />
              </div>
              <span
                className="text-[13px] font-medium text-right"
                style={{
                  color: isDark ? 'var(--color-text-1)' : '#1f2329',
                  minWidth: 45,
                }}
              >
                {item.value.toLocaleString()}
              </span>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

export default TopN;
