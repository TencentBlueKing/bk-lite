import React, { useEffect, useState, useRef } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Empty } from 'antd';
import { formatNumericValue } from '@/app/log/utils/common';
import useChartColors from './useChartColors';

interface DockerKpiCardProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const DockerKpiCard: React.FC<DockerKpiCardProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const colors = useChartColors();
  const [currentValue, setCurrentValue] = useState<number>();
  const [changePercent, setChangePercent] = useState<number | null>(null);
  const [trendData, setTrendData] = useState<number[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  const accentColor = config?.color || colors.primary;

  useEffect(() => {
    if (!loading && rawData) {
      const field = config?.displayMaps?.value;
      if (field && Array.isArray(rawData) && rawData.length > 0) {
        const values = rawData.map((item: any) => {
          const v = parseFloat(item[field]);
          return isNaN(v) ? 0 : v;
        });

        if (values.length > 1) {
          setTrendData(values);
          const total = values.reduce((sum: number, v: number) => sum + v, 0);
          setCurrentValue(total);

          const lastVal = values[values.length - 1];
          const prevVal = values[values.length - 2];
          if (prevVal !== 0) {
            setChangePercent(((lastVal - prevVal) / prevVal) * 100);
          } else {
            setChangePercent(null);
          }
        } else {
          const parsed = parseFloat(rawData[0][field]);
          setCurrentValue(isNaN(parsed) ? undefined : parsed);
          setTrendData([]);
          setChangePercent(null);
        }
      }
    }
  }, [rawData, loading, config]);

  const sparklineOption = {
    animation: false,
    grid: { top: 4, right: 0, bottom: 4, left: 0 },
    xAxis: {
      type: 'category' as const,
      show: false,
      data: trendData.map((_, i) => i)
    },
    yAxis: { type: 'value' as const, show: false },
    series: [
      {
        type: 'line' as const,
        data: trendData,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color: accentColor },
        areaStyle: {
          opacity: 0.15,
          color: accentColor
        }
      }
    ]
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div
          className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: `${accentColor}33`, borderTopColor: 'transparent' }}
        />
      </div>
    );
  }

  if (currentValue === undefined) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  const isUp = changePercent !== null && changePercent > 0;
  const isDown = changePercent !== null && changePercent < 0;

  return (
    <div
      ref={containerRef}
      className="flex flex-col h-full w-full rounded-lg overflow-hidden px-4 py-3"
      style={{ background: 'var(--color-fill-1)' }}
    >
        {/* 标题 */}
        <div
          className="text-xs truncate mb-1"
          style={{ color: 'var(--color-text-3)' }}
        >
          {config?.metricLabel || ''}
        </div>

        {/* 数值 + 环比 */}
        <div className="flex items-end justify-between mb-1">
          <span
            className="text-2xl font-bold leading-none"
            style={{ color: accentColor }}
          >
            {formatNumericValue(currentValue)}
          </span>
          {changePercent !== null ? (
            <span
              className="text-xs font-medium leading-none pb-0.5"
              style={{
                color: isUp
                  ? colors.danger
                  : isDown
                    ? colors.success
                    : colors.textTertiary
              }}
            >
              {isUp ? '↑' : isDown ? '↓' : ''}
              {changePercent > 0 ? '+' : ''}
              {changePercent.toFixed(1)}%
            </span>
          ) : (
            <span
              className="text-xs leading-none pb-0.5"
              style={{ color: colors.textTertiary }}
            >
              --
            </span>
          )}
        </div>

        {/* sparkline */}
        <div className="flex-1 min-h-0">
          {trendData.length > 1 ? (
            <ReactEcharts
              option={sparklineOption}
              style={{ height: '100%', width: '100%' }}
              opts={{ renderer: 'svg' }}
            />
          ) : (
            <div className="h-full" />
          )}
        </div>
    </div>
  );
};

export default DockerKpiCard;
