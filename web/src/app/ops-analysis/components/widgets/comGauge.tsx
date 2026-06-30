import React, { useEffect, useMemo } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty, Spin } from 'antd';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import {
  formatDisplayValue,
  getColorByThreshold,
} from '@/app/ops-analysis/utils/thresholdUtils';
import {
  extractComparableValue,
  toComparableNumber,
} from '@/app/ops-analysis/utils/compareQuery';
import { applyValueMapping } from '@/app/ops-analysis/utils/valueMapping';

interface ComGaugeProps {
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

const buildAxisLineColor = (
  min: number,
  max: number,
  thresholds: Array<{ value: string; color: string }> = [],
): Array<[number, string]> => {
  if (!thresholds.length || max <= min) {
    return [[1, '#366CE4']];
  }

  const range = max - min;
  const sorted = [...thresholds]
    .map((item) => ({
      value: Number(item.value),
      color: item.color,
    }))
    .filter((item) => Number.isFinite(item.value))
    .sort((a, b) => a.value - b.value);

  if (!sorted.length) {
    return [[1, '#366CE4']];
  }

  const axisLine: Array<[number, string]> = [];
  sorted.forEach((item, index) => {
    const ratio = clamp((item.value - min) / range, 0, 1);
    if (index === sorted.length - 1) {
      axisLine.push([1, item.color]);
      return;
    }
    axisLine.push([ratio, item.color]);
  });

  if (!axisLine.length) {
    return [[1, sorted[sorted.length - 1].color]];
  }

  return axisLine;
};

const ComGauge: React.FC<ComGaugeProps> = ({
  rawData,
  loading = false,
  config,
  onReady,
}) => {
  const selectedField = config?.selectedFields?.[0];
  const numericValue = toComparableNumber(
    extractComparableValue(rawData, selectedField),
  );
  const min = Number(config?.gaugeMin ?? 0);
  const max = Number(config?.gaugeMax ?? 100);
  const safeMin = Number.isFinite(min) ? min : 0;
  const safeMax = Number.isFinite(max) && max > safeMin ? max : safeMin + 100;
  const thresholds = config?.thresholdColors || [];
  const hasData = numericValue !== null;
  const usesScreenDarkTheme = config?.chartThemeMode === 'screen-dark';

  // 值映射：命中颜色覆盖阈值色；命中文本替换中心展示
  const valueMapping = applyValueMapping(numericValue, config?.valueMappings);
  const color =
    valueMapping?.color || getColorByThreshold(numericValue, thresholds, '#366CE4');

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

  useEffect(() => {
    if (!loading) {
      onReady?.(hasData);
    }
  }, [hasData, loading, onReady]);

  const option = useMemo(() => {
    const isCircle = config?.gaugeShape === 'circle';
    const currentValue = clamp(numericValue ?? safeMin, safeMin, safeMax);

    return {
      animation: true,
      series: [
        {
          type: 'gauge',
          min: safeMin,
          max: safeMax,
          startAngle: isCircle ? 225 : 180,
          endAngle: isCircle ? -45 : 0,
          center: ['50%', isCircle ? '52%' : '74%'],
          radius: usesScreenDarkTheme
            ? isCircle ? '82%' : '118%'
            : isCircle ? '90%' : '108%',
          progress: {
            show: true,
            roundCap: true,
            width: usesScreenDarkTheme ? 24 : 14,
            itemStyle: {
              color,
              shadowBlur: usesScreenDarkTheme ? 18 : 0,
              shadowColor: color,
            },
          },
          axisLine: {
            roundCap: true,
            lineStyle: {
              width: usesScreenDarkTheme ? 24 : 14,
              color: usesScreenDarkTheme
                ? [[1, 'rgba(56, 189, 248, 0.16)']]
                : buildAxisLineColor(safeMin, safeMax, thresholds),
            },
          },
          axisTick: {
            show: false,
          },
          splitLine: {
            length: usesScreenDarkTheme ? 14 : 10,
            distance: usesScreenDarkTheme ? -24 : -16,
            lineStyle: {
              width: usesScreenDarkTheme ? 3 : 2,
              color: usesScreenDarkTheme
                ? 'rgba(186, 230, 253, 0.28)'
                : '#FFFFFF',
            },
          },
          axisLabel: {
            distance: usesScreenDarkTheme ? 24 : 18,
            color: usesScreenDarkTheme
              ? 'rgba(186, 230, 253, 0.64)'
              : '#7A869A',
            fontSize: usesScreenDarkTheme ? 22 : 11,
          },
          pointer: {
            show: !usesScreenDarkTheme,
            length: '68%',
            width: 4,
          },
          anchor: {
            show: !usesScreenDarkTheme,
            size: usesScreenDarkTheme ? 0 : 9,
            itemStyle: {
              color,
            },
          },
          detail: {
            valueAnimation: true,
            offsetCenter: [0, isCircle ? '66%' : '38%'],
            fontSize: usesScreenDarkTheme ? 52 : 26,
            fontWeight: usesScreenDarkTheme ? 800 : 600,
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
    numericValue,
    safeMax,
    safeMin,
    thresholds,
    usesScreenDarkTheme,
  ]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!hasData) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <ReactEcharts option={option} style={{ height: '100%', width: '100%' }} />
  );
};

export default ComGauge;
