import React, { useEffect, useMemo } from 'react';
import { useWidgetDataLink } from '@/app/ops-analysis/components/interactionTitleIcon';
import DataLinkHintTooltip from '@/app/ops-analysis/components/dataLinkHintTooltip';
import { topNLinkPoints } from '@/app/ops-analysis/utils/interactionPoints';
import { Spin } from 'antd';
import WidgetState from '@/app/ops-analysis/components/widget-state';
import {
  getOpsChartColorsByMode,
  getOpsChartThemeByMode,
  isScreenChartThemeMode,
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
import {
  getScreenWidgetScale,
  scaleScreenMetric,
} from './shared/screenMetrics';
import { isTopNContentReady, resolveTopNContentState } from '@/app/ops-analysis/utils/topNContentState';
import { formatVisibleChartValue } from '@/app/ops-analysis/utils/chartValueFormat';
import {
  buildTopNItems,
  resolveConfiguredTopNBarPercent,
} from '@/app/ops-analysis/utils/topNData';
import { resolveChartBinding } from '@/app/ops-analysis/utils/chartFieldContract';

interface TopNProps {
  rawData: any;
  loading?: boolean;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  screenRenderContext?: ScreenRenderContext;
  onReady?: (ready: boolean) => void;
  componentSwitchControl?: React.ReactNode;
  errorMessage?: string;
}

export interface TopNHeaderParts {
  full: string;
  title: string;
  key: string;
}

export const resolveTopNHeaderParts = (
  fieldKey?: string,
  fieldSchema?: ResponseFieldDefinition[],
  options?: { preferTitleOnly?: boolean },
): TopNHeaderParts => {
  const key = String(fieldKey || '').trim();
  if (!key) return { full: '', title: '', key: '' };

  const field = (fieldSchema || []).find((item) => item.key === key);
  const title = String(field?.title || '').trim();

  if (!title) {
    // 大屏主题只显示中文 title；字段不在 schema 里时不能把列头留空。
    return { full: key, title: '', key };
  }

  if (options?.preferTitleOnly) {
    return { full: title, title, key: '' };
  }

  return { full: `${title}（${key}）`, title, key };
};

const mergeResultFieldTitles = (
  schema: ResponseFieldDefinition[] | undefined,
): ResponseFieldDefinition[] => schema || [];

export const resolveTopNHeaderLabel = (
  fieldKey?: string,
  fieldSchema?: ResponseFieldDefinition[],
  options?: { preferTitleOnly?: boolean },
) => resolveTopNHeaderParts(fieldKey, fieldSchema, options).full;

const TopN: React.FC<TopNProps> = ({
  rawData,
  loading = false,
  config,
  dataSource,
  screenRenderContext,
  onReady,
  componentSwitchControl,
  errorMessage,
}) => {
  const themeName = resolveOpsChartThemeName();
  const isDark = themeName === 'dark';
  const usesScreenChartTheme = isScreenChartThemeMode(config?.chartThemeMode);
  const chartTheme = getOpsChartThemeByMode(config?.chartThemeMode);
  const barColors = getOpsChartColorsByMode(config?.chartThemeMode, themeName);
  const widgetScale = getScreenWidgetScale(screenRenderContext);
  const binding = resolveChartBinding(rawData, {
    dimensionField: config?.topNLabelField,
    valueField: config?.topNValueField,
  });
  const labelField = config?.topNLabelField?.trim() || binding.dimensionField;
  const valueField = config?.topNValueField?.trim() || binding.measureField;
  const headerFields = mergeResultFieldTitles(dataSource?.field_schema);
  // 表头：中文 title 在前、字段 id 在括号；整段同色同重，不再分两套样式。
  const labelHeaderParts = resolveTopNHeaderParts(
    labelField,
    headerFields,
    { preferTitleOnly: usesScreenChartTheme },
  );
  const valueHeaderParts = resolveTopNHeaderParts(
    valueField,
    headerFields,
    { preferTitleOnly: usesScreenChartTheme },
  );
  const labelHeader = labelHeaderParts.full;
  const valueHeader = valueHeaderParts.full;
  // 名称按最长内容占宽，数值只留够显示的位置，剩余给进度条；进度条保留最小宽度，避免被长名称挤没。
  const columnGap = scaleScreenMetric(8, screenRenderContext);
  const cellPadding = scaleScreenMetric(8, screenRenderContext);
  const minBarWidth = scaleScreenMetric(56, screenRenderContext);
  const gridTemplateColumns = `minmax(0, max-content) minmax(${minBarWidth}px, 1fr) max-content`;
  const items = buildTopNItems(rawData, labelField, valueField, {
    scalarFields: config?.topNScalarFields,
  });
  const { active: dataLinkActive, openPoint, hoverHint } = useWidgetDataLink(config);
  const points = useMemo(
    () => topNLinkPoints(items, valueField),
    [items, valueField],
  );
  const isDataReady = items.length > 0;
  const contentState = resolveTopNContentState({
    loading,
    errorMessage,
    hasRows: isDataReady,
  });

  useEffect(() => {
    onReady?.(isTopNContentReady(contentState));
  }, [contentState, onReady]);

  let content: React.ReactNode;
  if (contentState === 'loading') {
    content = (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
      </div>
    );
  } else if (contentState === 'error') {
    content = <WidgetState kind="error" description={errorMessage} />;
  } else if (contentState === 'empty') {
    content = <WidgetState />;
  } else {
    content = (
      <div
        className="flex h-full min-h-0 flex-col overflow-hidden"
        style={{
          paddingBottom: scaleScreenMetric(4, screenRenderContext),
          paddingLeft: scaleScreenMetric(12, screenRenderContext),
          paddingRight: scaleScreenMetric(12, screenRenderContext),
          paddingTop: scaleScreenMetric(8, screenRenderContext),
        }}
      >
        {(labelHeader || valueHeader) && (
          <div
            className="grid shrink-0 items-center rounded-md"
            style={{
              gridTemplateColumns,
              columnGap,
              fontSize: 12 * widgetScale,
              paddingBottom: scaleScreenMetric(6, screenRenderContext),
              paddingTop: scaleScreenMetric(2, screenRenderContext),
            }}
          >
            <span
              className="min-w-0 truncate whitespace-nowrap"
              style={{
                paddingLeft: cellPadding,
                paddingRight: cellPadding,
                color: usesScreenChartTheme
                  ? chartTheme.axisLabelColor
                  : isDark ? 'rgba(255,255,255,0.72)' : '#5b6b85',
                fontWeight: 500,
              }}
              title={labelHeader}
            >
              {labelHeader}
            </span>
            <span aria-hidden="true" />
            <span
              className="whitespace-nowrap text-right"
              style={{
                paddingLeft: cellPadding,
                paddingRight: cellPadding,
                color: usesScreenChartTheme
                  ? chartTheme.axisLabelColor
                  : isDark ? 'rgba(255,255,255,0.72)' : '#5b6b85',
                fontWeight: 500,
              }}
              title={valueHeader}
            >
              {valueHeader}
            </span>
          </div>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div
            className="grid items-center"
            style={{
              gridTemplateColumns,
              columnGap,
              rowGap: scaleScreenMetric(2, screenRenderContext),
            }}
          >
            {items.map((item, index) => {
              const percent = resolveConfiguredTopNBarPercent(item.value, items, config);

              return (
                <React.Fragment key={`${item.name}-${index}`}>
                  <DataLinkHintTooltip hint={hoverHint && <>{item.name}<br />{hoverHint}</>}>
                  <span
                    className={`flex h-7 min-w-0 items-center truncate whitespace-nowrap rounded-l-md text-[13px] ${dataLinkActive ? 'cursor-pointer' : ''}`}
                    onClick={dataLinkActive ? () => openPoint(points[index]) : undefined}
                    style={{
                      color: usesScreenChartTheme
                        ? chartTheme.axisLabelColor
                        : isDark ? 'rgba(255,255,255,0.82)' : '#26364f',
                      fontSize: 13 * widgetScale,
                      height: scaleScreenMetric(28, screenRenderContext),
                      minWidth: 0,
                      paddingLeft: cellPadding,
                      paddingRight: cellPadding,
                    }}
                    title={hoverHint ? undefined : item.name}
                  >
                    {item.name}
                  </span>
                  </DataLinkHintTooltip>
                  <DataLinkHintTooltip hint={hoverHint}>
                  <div
                    className={`flex min-w-0 items-center ${dataLinkActive ? 'cursor-pointer' : ''}`}
                    style={{
                      height: scaleScreenMetric(28, screenRenderContext),
                    }}
                    onClick={dataLinkActive ? () => openPoint(points[index]) : undefined}
                  >
                    <div
                      className="h-2.5 min-w-0 w-full overflow-hidden rounded-full"
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
                          width: `${percent}%`,
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
                  </DataLinkHintTooltip>
                  <DataLinkHintTooltip hint={hoverHint}>
                  <span
                    className={`flex items-center justify-end whitespace-nowrap text-right text-[13px] font-semibold tabular-nums ${dataLinkActive ? 'cursor-pointer' : ''}`}
                    onClick={dataLinkActive ? () => openPoint(points[index]) : undefined}
                    style={{
                      color: usesScreenChartTheme
                        ? chartTheme.pieValueColor
                        : isDark ? 'rgba(255,255,255,0.88)' : '#1f2d44',
                      fontSize: 13 * widgetScale,
                      height: scaleScreenMetric(28, screenRenderContext),
                      paddingLeft: cellPadding,
                      paddingRight: cellPadding,
                    }}
                  >
                    {formatVisibleChartValue(item.value, config)}
                  </span>
                  </DataLinkHintTooltip>
                </React.Fragment>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {componentSwitchControl ? (
        <div className="shrink-0 overflow-x-auto px-3 pt-2">
          {componentSwitchControl}
        </div>
      ) : null}
      <div className="min-h-0 flex-1">{content}</div>
    </div>
  );
};

export default TopN;
