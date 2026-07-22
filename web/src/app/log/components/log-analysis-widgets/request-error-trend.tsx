import React from 'react';
import { ChartDataTransformer } from '@/app/log/components/log-analysis-widgets/runtime';
import TimeSeriesComposedChart, {
  formatCompactAxisValue,
} from '@/components/time-series-composed-chart';
import useChartColors from '@/hooks/useChartColors';

export interface LogAnalysisRequestErrorTrendProps {
  rawData: any;
  loading?: boolean;
}

const LogAnalysisRequestErrorTrend: React.FC<LogAnalysisRequestErrorTrendProps> = ({
  rawData,
  loading = false,
}) => {
  const colors = useChartColors();

  return (
    <TimeSeriesComposedChart
      data={rawData}
      loading={loading}
      getXLabel={(item) => ChartDataTransformer.formatTimeValue(item._time)}
      series={[
        { name: '总请求数', type: 'bar', dataKey: 'total_count', color: colors.primary },
        {
          name: '4xx 请求数',
          type: 'line',
          dataKey: 'error4xx',
          color: colors.warning,
          showArea: true,
        },
        {
          name: '5xx 请求数',
          type: 'line',
          dataKey: 'error5xx',
          color: colors.danger,
          showArea: true,
        },
      ]}
      yAxes={[{ formatter: formatCompactAxisValue, minInterval: 1 }]}
    />
  );
};

export default LogAnalysisRequestErrorTrend;
