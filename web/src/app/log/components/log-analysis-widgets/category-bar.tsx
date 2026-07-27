import React, { useMemo } from 'react';
import HorizontalCategoryBarChart from '@/components/horizontal-category-bar-chart';
import useChartColors from '@/hooks/useChartColors';

interface LogAnalysisCategoryBarSeries {
  dataKey: string;
  label?: string;
  color?: string;
  colorIndex?: number;
  showLabel?: boolean;
}

interface LogAnalysisCategoryBarProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const trimTrailingZeros = (value: string) =>
  value.replace(/\.0+$|(?<=\.\d*[1-9])0+$/g, '');

const formatCompactNumber = (value: number): string => {
  if (!isFinite(value)) return '--';

  const absValue = Math.abs(value);
  if (absValue >= 1_000_000) {
    return `${trimTrailingZeros((value / 1_000_000).toFixed(absValue >= 10_000_000 ? 1 : 2))}M`;
  }
  if (absValue >= 1_000) {
    return `${trimTrailingZeros((value / 1_000).toFixed(absValue >= 100_000 ? 0 : 1))}k`;
  }
  return Number.isInteger(value)
    ? String(value)
    : trimTrailingZeros(value.toFixed(2));
};

const normalizeFieldKey = (field: string) => field.replace(/^"|"$/g, '');

const getFieldValue = (item: any, field: string) => {
  if (!field) return undefined;
  if (item[field] !== undefined) return item[field];

  const normalizedField = normalizeFieldKey(field);
  if (normalizedField !== field && item[normalizedField] !== undefined) {
    return item[normalizedField];
  }

  return undefined;
};

const toNumber = (value: unknown) => {
  const num = Number.parseFloat(String(value ?? 0));
  return Number.isNaN(num) ? 0 : num;
};

const normalizeCategoryLabel = (value: unknown) => {
  if (value === null || value === undefined || value === '') return '-';
  return String(value);
};

const LogAnalysisCategoryBar: React.FC<LogAnalysisCategoryBarProps> = ({
  rawData,
  loading = false,
  config,
}) => {
  const colors = useChartColors();

  const chartData = useMemo(() => {
    if (!Array.isArray(rawData) || rawData.length === 0) {
      return null;
    }

    const displayMaps = config?.displayMaps || {};
    const nameField = displayMaps.key || 'name';
    const configuredSeries: LogAnalysisCategoryBarSeries[] =
      config?.series ||
      [
        {
          dataKey: displayMaps.value || 'count',
          color: config?.barColor,
          showLabel: true,
        },
      ];

    const items = rawData
      .map((item: any) => ({
        name: normalizeCategoryLabel(getFieldValue(item, nameField)),
        values: configuredSeries.map((seriesItem) =>
          toNumber(getFieldValue(item, seriesItem.dataKey))
        ),
      }))
      .sort((a, b) => a.values[0] - b.values[0]);

    return {
      categories: items.map((item) => item.name),
      series: configuredSeries.map((seriesItem, index) => ({
        name: seriesItem.label,
        data: items.map((item) => item.values[index]),
        color:
          seriesItem.color ||
          colors.series[seriesItem.colorIndex ?? index] ||
          colors.primary,
        showLabel: seriesItem.showLabel ?? configuredSeries.length === 1,
      })),
    };
  }, [colors, config, rawData]);

  return (
    <HorizontalCategoryBarChart
      loading={loading}
      theme={colors}
      categories={chartData?.categories || []}
      series={(chartData?.series || []).map((item) => ({
        ...item,
        labelFormatter: formatCompactNumber,
      }))}
      reverse={false}
      categoryLabelWidth={config?.categoryLabelWidth || 60}
      categoryLabelMaxLength={config?.categoryLabelMaxLength || 12}
      axisLabelFontSize={config?.axisLabelFontSize || 10}
      valueAxisFormatter={formatCompactNumber}
      gridRight={config?.gridRight || 60}
      valueAxisSplitNumber={config?.valueAxisSplitNumber || 4}
      splitLineType={config?.splitLineType || 'solid'}
      showLegend={config?.showLegend}
    />
  );
};

export default LogAnalysisCategoryBar;
