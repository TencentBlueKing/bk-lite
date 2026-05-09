import React, { useEffect, useState, useRef } from 'react';
import ReactEcharts from 'echarts-for-react';
import { Spin, Empty } from 'antd';
import { formatNumericValue } from '@/app/log/utils/common';

interface ComKpiCardProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const ComKpiCard: React.FC<ComKpiCardProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const [currentValue, setCurrentValue] = useState<number>();
  const [changePercent, setChangePercent] = useState<number | null>(null);
  const [trendData, setTrendData] = useState<number[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loading && rawData) {
      const field = config?.displayMaps?.value;
      if (field && Array.isArray(rawData) && rawData.length > 0) {
        const values = rawData.map((item: any) => {
          const v = parseFloat(item[field]);
          return isNaN(v) ? 0 : v;
        });

        if (values.length > 1) {
          // 时序数据：sparkline 用所有点，总值用 sum
          setTrendData(values);
          const total = values.reduce((sum: number, v: number) => sum + v, 0);
          setCurrentValue(total);

          // 环比：最后一个点 vs 倒数第二个点
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
    grid: { top: 2, right: 2, bottom: 2, left: 2 },
    xAxis: { type: 'category' as const, show: false, data: trendData.map((_, i) => i) },
    yAxis: { type: 'value' as const, show: false },
    series: [
      {
        type: 'line' as const,
        data: trendData,
        smooth: true,
        symbol: 'none',
        lineStyle: {
          width: 1.5,
          color: config?.color || 'var(--color-primary)'
        },
        areaStyle: {
          opacity: 0.15,
          color: config?.color || 'var(--color-primary)'
        }
      }
    ]
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
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
      className="flex flex-col h-full w-full rounded-lg px-4 py-3"
      style={{ background: 'var(--color-fill-1)' }}
    >
      {/* 标题行 */}
      <div
        className="text-xs mb-1 truncate"
        style={{ color: 'var(--color-text-3)' }}
      >
        {config?.metricLabel || ''}
      </div>

      {/* 数值(左) + 环比(右) */}
      <div className="flex items-end justify-between mb-1">
        <span
          className="text-2xl font-semibold leading-none"
          style={{ color: config?.color || 'var(--color-text-1)' }}
        >
          {formatNumericValue(currentValue)}
        </span>
        {changePercent !== null ? (
          <span
            className="text-xs font-medium leading-none pb-0.5"
            style={{
              color: isUp
                ? 'var(--color-fail)'
                : isDown
                  ? 'var(--color-success)'
                  : 'var(--color-text-3)'
            }}
          >
            {isUp ? '↑' : isDown ? '↓' : ''}
            {changePercent > 0 ? '+' : ''}
            {changePercent.toFixed(1)}%
          </span>
        ) : (
          <span
            className="text-xs leading-none pb-0.5"
            style={{ color: 'var(--color-text-4)' }}
          >
            --
          </span>
        )}
      </div>

      {/* 迷你趋势线 */}
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

export default ComKpiCard;
