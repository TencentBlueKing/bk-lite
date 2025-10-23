import {
  BarChart as ReBarChart,
  ResponsiveContainer,
  Bar,
  XAxis,
  YAxis,
  Tooltip
} from "recharts";
import { Empty } from 'antd';
import { useCallback, useMemo } from "react";
import chartLineStyle from './index.module.scss';

interface BarChartProps {
  data: any[],
  layout?: 'vertical' | 'horizontal'
}

const BarChart: React.FC<BarChartProps> = ({
  data = [],
  layout = 'horizontal'
}) => {

  const getChartAreaKeys = useCallback((arr: any[]): string[] => {
    const keys = new Set<string>();
    arr.forEach((obj) => {
      Object.keys(obj).forEach((key) => {
        if (key.includes('value')) {
          keys.add(key);
        }
      });
    });
    return Array.from(keys);
  }, []);

  const chartKeys = useMemo(() => {
    const keys = getChartAreaKeys(data);
    console.log(keys);
    return keys;
  }, [data, getChartAreaKeys]);

  return (
    <div className="w-full h-full flex flex-col">
      {!!data.length ? (
        <ResponsiveContainer className={`${chartLineStyle.chart}`}>
          <ReBarChart
            data={data}
            layout={layout}
            margin={{
              top: 10,
              right: 0,
              left: 0,
              bottom: 0,
            }}
          >
            <XAxis
              type={layout === "horizontal" ? "category" : "number"}
              dataKey={layout === "horizontal" ? undefined : "value"}
            />
            <YAxis
              tick={layout === "horizontal"}
              type={layout === "horizontal" ? "number" : "category"}
              dataKey={layout === "horizontal" ? "value" : undefined}
            />
            <Tooltip />
            {chartKeys?.map((key, index) => (
              <Bar key={index} dataKey={key} fill="#1976d2" />
            ))}
          </ReBarChart>
        </ResponsiveContainer>
      ) : (
        <div className={`${chartLineStyle.chart} ${chartLineStyle.noData}`}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
    </div>
  )
};

export default BarChart;