import React, { useCallback, useMemo, useRef } from 'react';
import ReactEcharts from 'echarts-for-react';
import { useWidgetDataLink } from '@/app/ops-analysis/components/interactionTitleIcon';
import { buildInteractionPoints } from '@/app/ops-analysis/utils/interactionPoints';
import { readRadarClickGeometry } from '@/app/ops-analysis/utils/interactionBehavior';
import type { ChartClickParams } from '@/app/ops-analysis/utils/interactionLink';
import ChartSurface from '@/components/chart-surface';
import type { ValueConfig } from '@/app/ops-analysis/components/ops-analysis-widgets';
import { randomColorForLegend } from '@/app/ops-analysis/components/ops-analysis-widgets/runtime';
import { getOpsChartThemeByMode, resolveOpsChartThemeName } from '@/app/ops-analysis/utils/chartTheme';
import {
  escapeInteractionTooltipHtml,
  resolveDataLinkTooltipTheme,
  wrapDataLinkTooltipFormatter,
} from '@/app/ops-analysis/utils/interactionLinkHint';
import { useEchartsFinishedReady } from '@/app/ops-analysis/hooks/useEchartsFinishedReady';
import {
  normalizeRadarRange,
  resolveRadarSeriesData,
} from '@/app/ops-analysis/utils/radarData';
import { useTranslation } from '@/utils/i18n';

export interface OpsAnalysisRadarProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

const OpsAnalysisRadar: React.FC<OpsAnalysisRadarProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const { t } = useTranslation();
  const chartTheme = getOpsChartThemeByMode(config?.chartThemeMode);
  const seriesColor = randomColorForLegend()[0];
  const radarConfig = config?.radar;
  const range = normalizeRadarRange(radarConfig, {
    gaugeMin: config?.gaugeMin,
    gaugeMax: config?.gaugeMax,
  });
  const radarSeries = useMemo(
    () =>
      resolveRadarSeriesData(rawData, radarConfig, config?.selectedFields || []),
    [config?.selectedFields, radarConfig, rawData],
  );
  const hasData = radarSeries.indicatorLabels.length > 0;
  const { onEvents: finishedEvents } = useEchartsFinishedReady({
    loading,
    isDataReady: hasData,
    onReady,
  });
  const { onChartClick, link, surface, chartTooltipHint } = useWidgetDataLink(config);
  const linkTooltipTheme = resolveDataLinkTooltipTheme(
    config?.chartThemeMode,
    resolveOpsChartThemeName(),
  );
  const chartRef = useRef<ReactEcharts>(null);
  const radarPoints = useMemo(
    () => buildInteractionPoints('radar', rawData, config),
    [config, rawData],
  );
  const onRadarClick = useCallback((params: ChartClickParams) => {
    const radar = readRadarClickGeometry(
      chartRef.current?.getEchartsInstance?.(),
      radarPoints.length,
    );
    onChartClick(radar ? { ...params, radar } : params);
  }, [onChartClick, radarPoints.length]);
  const onEvents = useMemo(
    () => ({ ...finishedEvents, click: onRadarClick }),
    [finishedEvents, onRadarClick],
  );

  const option = useMemo(
    () => {
      const linkFormatter = wrapDataLinkTooltipFormatter(undefined, {
        surface,
        link,
        footerText: chartTooltipHint,
        theme: linkTooltipTheme,
        fallback: () => {
          const rows = radarSeries.indicatorLabels.map((label, index) => {
            const value = radarSeries.indicatorValues[index];
            return `${escapeInteractionTooltipHtml(String(label))}: ${escapeInteractionTooltipHtml(value == null ? '' : String(value))}`;
          }).join('<br/>');
          return `<div>${rows}</div>`;
        },
      });
      return ({
        tooltip: {
          trigger: 'item',
          confine: true,
          backgroundColor: chartTheme.tooltipBackgroundColor,
          borderWidth: 1,
          borderColor: chartTheme.tooltipBorderColor,
          extraCssText: `box-shadow: ${chartTheme.tooltipShadow};`,
          textStyle: { color: chartTheme.tooltipTextColor },
          ...(linkFormatter ? { formatter: linkFormatter } : {}),
        },
        radar: {
          indicator: radarSeries.indicatorLabels.map((label) => ({
            name: label,
            min: range.min,
            max: range.max,
          })),
          axisName: { color: chartTheme.axisLabelColor },
          axisLine: { lineStyle: { color: chartTheme.axisLineColor } },
          splitLine: { lineStyle: { color: chartTheme.splitLineColor } },
        },
        series: [
          {
            type: 'radar',
            data: [
              {
                value: radarSeries.indicatorValues,
                __links: radarPoints,
                areaStyle: {
                  color: seriesColor,
                  opacity: chartTheme.lineAreaOpacity,
                },
              },
            ],
            lineStyle: {
              width: chartTheme.lineWidth,
              color: seriesColor,
              opacity: chartTheme.lineOpacity,
            },
            itemStyle: { color: seriesColor },
          },
        ],
      });
    },
    [
      chartTheme.axisLabelColor,
      chartTheme.axisLineColor,
      chartTheme.lineAreaOpacity,
      chartTheme.lineOpacity,
      chartTheme.lineWidth,
      chartTheme.splitLineColor,
      chartTheme.tooltipBackgroundColor,
      chartTheme.tooltipBorderColor,
      chartTheme.tooltipShadow,
      chartTheme.tooltipTextColor,
      radarPoints,
      radarSeries.indicatorLabels,
      radarSeries.indicatorValues,
      range.max,
      range.min,
      seriesColor,
      surface,
      link,
      chartTooltipHint,
      linkTooltipTheme,
    ],
  );

  return (
    <ChartSurface
      loading={loading}
      hasData={hasData}
      containerClassName="flex h-full min-h-0 w-full flex-col p-3"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="flex h-full w-full items-center justify-center"
    >
      {radarSeries.warning ? (
        <div className="mb-2 text-xs text-(--color-warning)">
          {radarSeries.warning === 'few_indicators'
            ? t('dashboard.radarFewIndicatorsWarning')
            : t('dashboard.radarTooManyIndicatorsWarning')}
        </div>
      ) : null}
      <div className="min-h-0 flex-1">
        <ReactEcharts
          ref={chartRef}
          option={option}
          onEvents={onEvents}
          style={{ height: '100%', width: '100%' }}
        />
      </div>
    </ChartSurface>
  );
};

export default OpsAnalysisRadar;
