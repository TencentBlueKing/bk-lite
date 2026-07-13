import React, { useEffect } from 'react';
import { Spin, Empty } from 'antd';
import {
  getOpsChartColorsByMode,
  getOpsChartThemeByMode,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import {
  ScreenRenderContext,
  ValueConfig,
} from '@/app/ops-analysis/types/dashBoard';
import type {
  DatasourceItem,
  ResponseFieldDefinition,
} from '@/app/ops-analysis/types/dataSource';
import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';
import {
  getScreenWidgetScale,
  scaleScreenMetric,
} from './shared/screenMetrics';

interface TopNProps {
  rawData: any;
  loading?: boolean;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  screenRenderContext?: ScreenRenderContext;
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

export const resolveTopNHeaderLabel = (
  fieldKey?: string,
  fieldSchema?: ResponseFieldDefinition[],
  options?: { preferTitleOnly?: boolean },
) => {
  const key = String(fieldKey || '').trim();
  if (!key) return '';

  const field = (fieldSchema || []).find((item) => item.key === key);
  const title = String(field?.title || '').trim();

  if (!title) return options?.preferTitleOnly ? '' : key;

  return options?.preferTitleOnly ? title : `${key}（${title}）`;
};

const TopN: React.FC<TopNProps> = ({
  rawData,
  loading = false,
  config,
  dataSource,
  screenRenderContext,
  onReady,
}) => {
  const themeName = resolveOpsChartThemeName();
  const isDark = themeName === 'dark';
  const usesScreenChartTheme =
    config?.chartThemeMode === 'screen-dark' ||
    config?.chartThemeMode === 'screen-light';
  const chartTheme = getOpsChartThemeByMode(config?.chartThemeMode);
  const barColors = getOpsChartColorsByMode(config?.chartThemeMode, themeName);
  const widgetScale = getScreenWidgetScale(screenRenderContext);
  const labelField = config?.topNLabelField;
  const valueField = config?.topNValueField;
  const labelHeader = resolveTopNHeaderLabel(
    labelField,
    dataSource?.field_schema,
    { preferTitleOnly: usesScreenChartTheme },
  );
  const valueHeader = resolveTopNHeaderLabel(
    valueField,
    dataSource?.field_schema,
    { preferTitleOnly: usesScreenChartTheme },
  );

  const transformData = (data: any): TopNItem[] => {
    const rows = unwrapTopNData(data);
    if (rows.length === 0) return [];

    // [[name, value], ...] format
    if (Array.isArray(rows[0])) {
      return rows
        .map((item: any[]) => {
          const rawName = getValueByPath(item, labelField);
          const rawValue = getValueByPath(item, valueField);

          const name =
            rawName === undefined || rawName === null
              ? ''
              : String(rawName).trim();
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

    // [{name, value}] format
    if (typeof rows[0] === 'object') {
      return rows
        .map((item: any) => {
          const rawName = getValueByPath(item, labelField);
          const rawValue = getValueByPath(item, valueField);

          const name =
            rawName === undefined || rawName === null
              ? ''
              : String(rawName).trim();
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
  const maxValue =
    items.length > 0 ? Math.max(...items.map((i) => i.value)) : 0;
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
    <div
      className="h-full overflow-y-auto"
      style={{
        paddingBottom: scaleScreenMetric(4, screenRenderContext),
        paddingLeft: scaleScreenMetric(12, screenRenderContext),
        paddingRight: scaleScreenMetric(12, screenRenderContext),
        paddingTop: scaleScreenMetric(8, screenRenderContext),
      }}
    >
      {(labelHeader || valueHeader) && (
        <div
          className="grid items-center rounded-md font-medium"
          style={{
            gridTemplateColumns: 'minmax(112px, 28%) minmax(0, 1fr) minmax(48px, auto)',
            columnGap: scaleScreenMetric(12, screenRenderContext),
            color: usesScreenChartTheme
              ? chartTheme.singleValueMetaColor
              : isDark ? 'rgba(255,255,255,0.66)' : '#5f6f89',
            fontSize: 12 * widgetScale,
            marginBottom: scaleScreenMetric(6, screenRenderContext),
            paddingBottom: scaleScreenMetric(6, screenRenderContext),
            paddingTop: scaleScreenMetric(6, screenRenderContext),
          }}
        >
          <span className="truncate" title={labelHeader}>
            {labelHeader}
          </span>
          <span />
          <span className="text-right truncate" title={valueHeader}>
            {valueHeader}
          </span>
        </div>
      )}
      <div
        className="grid items-center"
        style={{
          gridTemplateColumns: 'minmax(112px, 28%) minmax(0, 1fr) minmax(48px, auto)',
          columnGap: scaleScreenMetric(12, screenRenderContext),
          rowGap: scaleScreenMetric(2, screenRenderContext),
        }}
      >
        {items.map((item, index) => {
          const percent = maxValue > 0 ? (item.value / maxValue) * 100 : 0;

          return (
            <React.Fragment key={`${item.name}-${index}`}>
              <span
                className="flex h-7 items-center truncate rounded-l-md px-2 text-[13px]"
                style={{
                  color: usesScreenChartTheme
                    ? chartTheme.axisLabelColor
                    : isDark ? 'rgba(255,255,255,0.82)' : '#26364f',
                  fontSize: 13 * widgetScale,
                  height: scaleScreenMetric(28, screenRenderContext),
                  minWidth: 0,
                  paddingLeft: scaleScreenMetric(8, screenRenderContext),
                  paddingRight: scaleScreenMetric(8, screenRenderContext),
                }}
                title={item.name}
              >
                {item.name}
              </span>
              <div
                className="flex min-w-0 items-center"
                style={{ height: scaleScreenMetric(28, screenRenderContext) }}
              >
                <div
                  className="h-2.5 w-full overflow-hidden rounded-full"
                  style={{
                    backgroundColor: usesScreenChartTheme
                      ? chartTheme.panelSubtleBg
                      : isDark ? 'rgba(255,255,255,0.09)' : '#e8eef8',
                    height: scaleScreenMetric(10, screenRenderContext),
                  }}
                >
                  <div
                    className="h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.max(percent, item.value > 0 ? 2 : 0)}%`,
                      background: usesScreenChartTheme && barColors.length > 0
                        ? `linear-gradient(90deg, ${barColors[index % barColors.length]} 0%, ${barColors[(index + 1) % barColors.length]} 100%)`
                        : isDark
                          ? 'linear-gradient(90deg, #5b8cff 0%, #2f6bff 100%)'
                          : 'linear-gradient(90deg, #4f7df3 0%, #235ee8 100%)',
                      boxShadow: usesScreenChartTheme
                        ? `0 0 ${scaleScreenMetric(chartTheme.topNBarShadowBlur, screenRenderContext)}px ${chartTheme.topNBarShadowColor}`
                        : 'none',
                    }}
                  />
                </div>
              </div>
              <span
                className="flex h-7 items-center justify-end rounded-r-md px-2 text-[13px] font-semibold tabular-nums"
                style={{
                  color: usesScreenChartTheme
                    ? chartTheme.pieValueColor
                    : isDark ? 'rgba(255,255,255,0.88)' : '#1f2d44',
                  fontSize: 13 * widgetScale,
                  height: scaleScreenMetric(28, screenRenderContext),
                  minWidth: scaleScreenMetric(48, screenRenderContext),
                  paddingLeft: scaleScreenMetric(8, screenRenderContext),
                  paddingRight: scaleScreenMetric(8, screenRenderContext),
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
