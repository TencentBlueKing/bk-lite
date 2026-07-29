import React from 'react';
import { ChartDataTransformer } from '@/app/log/components/log-analysis-widgets/runtime';
import TimeSeriesComposedChart, {
  formatCompactAxisValue,
} from '@/components/time-series-composed-chart';
import useChartColors from '@/hooks/useChartColors';

interface LogAnalysisDualTrendProps {
  rawData: any;
  loading?: boolean;
  xField?: string;
  fallbackXField?: string;
  primaryField: string;
  primaryLabel: string;
  secondaryField?: string;
  secondaryLabel?: string;
  hideSecondaryWhenEmpty?: boolean;
}

const toNumber = (value: unknown) => {
  const num = Number.parseFloat(String(value ?? 0));
  return Number.isNaN(num) ? 0 : num;
};

const LogAnalysisDualTrend: React.FC<LogAnalysisDualTrendProps> = ({
  rawData,
  loading = false,
  xField = '_time',
  fallbackXField,
  primaryField,
  primaryLabel,
  secondaryField,
  secondaryLabel,
  hideSecondaryWhenEmpty = false,
}) => {
  const colors = useChartColors();

  const hasSecondary = Boolean(
    secondaryField &&
      (!hideSecondaryWhenEmpty ||
        (Array.isArray(rawData) &&
          rawData.some((item: any) => toNumber(item?.[secondaryField]) > 0)))
  );

  return (
    <TimeSeriesComposedChart
      data={rawData}
      loading={loading}
      legendVisible={hasSecondary}
      xAxisBoundaryGap={false}
      axisLabelFontSize={10}
      grid={{
        top: hasSecondary ? 36 : 16,
        left: 52,
        right: hasSecondary ? 52 : 16,
        bottom: 24,
      }}
      getXLabel={(item) =>
        ChartDataTransformer.formatTimeValue(
          item[xField] ?? (fallbackXField ? item[fallbackXField] : undefined)
        )
      }
      series={[
        {
          name: primaryLabel,
          type: 'line',
          dataKey: primaryField,
          color: colors.series[0],
          yAxisIndex: 0,
          showArea: true,
          smooth: true,
        },
        ...(hasSecondary && secondaryField
          ? [
            {
              name: secondaryLabel || secondaryField,
              type: 'line' as const,
              dataKey: secondaryField,
              color: colors.series[4],
              yAxisIndex: 1,
              showArea: true,
              smooth: true,
            },
          ]
          : []),
      ]}
      yAxes={
        hasSecondary
          ? [
            { formatter: formatCompactAxisValue },
            { formatter: formatCompactAxisValue, splitLine: false },
          ]
          : [{ formatter: formatCompactAxisValue }]
      }
    />
  );
};

export default LogAnalysisDualTrend;
