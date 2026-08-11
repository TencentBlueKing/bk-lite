import React, { useEffect, useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import ChartSurface from '@/components/chart-surface';
import type { ValueConfig } from '@/app/ops-analysis/components/ops-analysis-widgets';
import {
  getOpsChartTheme,
  randomColorForLegend,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/components/ops-analysis-widgets/runtime';
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
  const themeName = resolveOpsChartThemeName();
  const chartTheme = getOpsChartTheme(themeName);
  const seriesColor = randomColorForLegend(themeName)[0];
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

  useEffect(() => {
    if (!loading) {
      onReady?.(hasData);
    }
  }, [hasData, loading, onReady]);

  const option = useMemo(
    () => ({
      tooltip: {
        trigger: 'item',
        backgroundColor: chartTheme.tooltipBackgroundColor,
        borderColor: chartTheme.tooltipBorderColor,
        textStyle: { color: chartTheme.tooltipTextColor },
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
    }),
    [
      chartTheme.axisLabelColor,
      chartTheme.axisLineColor,
      chartTheme.lineAreaOpacity,
      chartTheme.lineOpacity,
      chartTheme.lineWidth,
      chartTheme.splitLineColor,
      chartTheme.tooltipBackgroundColor,
      chartTheme.tooltipBorderColor,
      chartTheme.tooltipTextColor,
      radarSeries.indicatorLabels,
      radarSeries.indicatorValues,
      range.max,
      range.min,
      seriesColor,
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
        <ReactEcharts option={option} style={{ height: '100%', width: '100%' }} />
      </div>
    </ChartSurface>
  );
};

export default OpsAnalysisRadar;
