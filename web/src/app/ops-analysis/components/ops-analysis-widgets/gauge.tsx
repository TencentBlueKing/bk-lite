import React, { useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import {
  applyValueMapping,
  formatDisplayValue,
  getColorByThreshold,
} from '@/app/ops-analysis/components/ops-analysis-config-sections';
import {
  extractComparableValue,
  toComparableNumber,
} from '@/app/ops-analysis/components/ops-analysis-widgets/runtime';
import type { ValueConfig } from '@/app/ops-analysis/components/ops-analysis-widgets';
import { useGaugeResponsiveLayout } from '@/app/ops-analysis/components/widgets/shared/useGaugeResponsiveLayout';
import { useEchartsFinishedReady } from '@/app/ops-analysis/hooks/useEchartsFinishedReady';
import { buildGaugeAxisLineColor } from '@/app/ops-analysis/utils/thresholdUtils';
import ChartSurface from '@/components/chart-surface';

export interface OpsAnalysisGaugeProps {
  rawData: unknown;
  loading?: boolean;
  config?: ValueConfig;
  onReady?: (ready: boolean) => void;
}

const clamp = (value: number, min: number, max: number) => {
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

const OpsAnalysisGauge: React.FC<OpsAnalysisGaugeProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const selectedField = config?.selectedFields?.[0];
  const numericValue = toComparableNumber(extractComparableValue(rawData, selectedField));
  const min = Number(config?.gaugeMin ?? 0);
  const max = Number(config?.gaugeMax ?? 100);
  const safeMin = Number.isFinite(min) ? min : 0;
  const safeMax = Number.isFinite(max) && max > safeMin ? max : safeMin + 100;
  const thresholds = config?.thresholdColors || [];
  const hasData = numericValue !== null;

  const valueMapping = applyValueMapping(numericValue, config?.valueMappings);
  const color = valueMapping?.color || getColorByThreshold(numericValue, thresholds, '#366CE4');
  const displayValue =
    valueMapping?.text !== undefined
      ? valueMapping.text
      : formatDisplayValue(
        numericValue,
        config?.unit,
        config?.decimalPlaces,
        config?.conversionFactor,
        config?.unitId,
      );

  const isCircle = config?.gaugeShape === 'circle';
  const { containerRef, chartRef, layout, geometry, hasValidContainerSize } = useGaugeResponsiveLayout({
    gaugeShape: config?.gaugeShape,
    desiredRadiusPercent: isCircle ? 90 : 108,
    desiredCenterPercent: [50, isCircle ? 56 : 72],
    axisLineWidth: 14,
  });
  const { onEvents } = useEchartsFinishedReady({
    loading,
    isDataReady: hasData,
    canReportReady: hasValidContainerSize,
    onReady,
  });

  const option = useMemo(() => {
    const currentValue = clamp(numericValue ?? safeMin, safeMin, safeMax);

    return {
      animation: true,
      series: [
        {
          type: 'gauge',
          min: safeMin,
          max: safeMax,
          splitNumber: layout.splitNumber,
          startAngle: isCircle ? 225 : 180,
          endAngle: isCircle ? -45 : 0,
          center: geometry.center,
          radius: geometry.radius,
          progress: {
            show: true,
            roundCap: true,
            width: 14,
            itemStyle: {
              color,
            },
          },
          axisLine: {
            roundCap: true,
            lineStyle: {
              width: 14,
              color: buildGaugeAxisLineColor(safeMin, safeMax, thresholds),
            },
          },
          axisTick: {
            show: false,
          },
          splitLine: {
            length: 10,
            // Negative distance keeps white ticks on the colored arc.
            distance: -16,
            lineStyle: {
              width: 2,
              color: '#FFFFFF',
            },
          },
          axisLabel: {
            distance: layout.axisLabelDistance,
            color: '#7A869A',
            fontSize: 11,
          },
          pointer: {
            show: true,
            length: '68%',
            width: 4,
          },
          anchor: {
            show: true,
            size: 9,
            itemStyle: {
              color,
            },
          },
          detail: {
            valueAnimation: true,
            offsetCenter: [0, layout.detailOffsetCenterY],
            fontSize: layout.detailFontSize,
            fontWeight: 600,
            color,
            formatter: () => displayValue,
          },
          data: [{ value: currentValue }],
        },
      ],
    };
  }, [
    color,
    config?.gaugeShape,
    displayValue,
    geometry.center,
    geometry.radius,
    layout.axisLabelDistance,
    layout.detailFontSize,
    layout.detailOffsetCenterY,
    layout.splitNumber,
    numericValue,
    safeMax,
    safeMin,
    thresholds,
  ]);

  return (
    <ChartSurface
      ref={containerRef}
      loading={loading}
      hasData={hasData}
      containerClassName="flex h-full w-full"
      loadingClassName="flex h-full w-full items-center justify-center"
      emptyClassName="flex h-full w-full items-center justify-center"
    >
      <ReactEcharts
        ref={chartRef}
        option={option}
        onEvents={onEvents}
        style={{ height: '100%', width: '100%' }}
      />
    </ChartSurface>
  );
};

export default OpsAnalysisGauge;
