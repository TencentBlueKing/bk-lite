import React from 'react';
import { ChartDataTransformer } from '@/app/log/components/log-analysis-widgets/runtime';
import TimeSeriesComposedChart, {
  formatCompactAxisValue,
} from '@/components/time-series-composed-chart';
import useChartColors from '@/hooks/useChartColors';

interface TrendMetricSeries {
  label: string;
  dataKey: string;
}

interface LogAnalysisMetricsTrendProps {
  rawData: any;
  loading?: boolean;
  primary: TrendMetricSeries;
  secondary: TrendMetricSeries[];
  primaryType?: 'bar' | 'line';
  xField?: string;
}

const LogAnalysisMetricsTrend: React.FC<LogAnalysisMetricsTrendProps> = ({
  rawData,
  loading = false,
  primary,
  secondary,
  primaryType = 'bar',
  xField = '_time',
}) => {
  const colors = useChartColors();
  const secondaryColors = [
    colors.danger,
    colors.warning,
    colors.series[5],
    colors.series[1],
    colors.series[2],
  ];

  return (
    <TimeSeriesComposedChart
      data={rawData}
      loading={loading}
      getXLabel={(item) => ChartDataTransformer.formatTimeValue(item[xField])}
      series={[
        {
          name: primary.label,
          type: primaryType,
          dataKey: primary.dataKey,
          color: colors.primary,
          ...(primaryType === 'line'
            ? {
              yAxisIndex: 0,
              lineWidth: 2.5,
              showArea: true,
            }
            : {}),
        },
        ...secondary.map((item, index) => ({
          name: item.label,
          type: 'line' as const,
          dataKey: item.dataKey,
          color: secondaryColors[index] || colors.series[index] || colors.primary,
          yAxisIndex: 1,
          showArea: true,
        })),
      ]}
      yAxes={[
        { formatter: formatCompactAxisValue, minInterval: 1 },
        { formatter: formatCompactAxisValue, minInterval: 1, splitLine: false },
      ]}
    />
  );
};

export default LogAnalysisMetricsTrend;
