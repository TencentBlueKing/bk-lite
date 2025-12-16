import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Empty } from 'antd';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  AreaChart,
  Area,
  ResponsiveContainer,
  ReferenceArea,
  ReferenceLine,
  Label,
  Brush
} from 'recharts';
import CustomTooltip from './customTooltips';
import {
  generateUniqueRandomColor,
  useFormatTime,
  isStringArray,
} from '@/app/mlops/utils/common';
import chartLineStyle from './index.module.scss';
import dayjs, { Dayjs } from 'dayjs';
// import DimensionFilter from './dimensionFilter';
// import DimensionTable from './dimensionTable';
import { ChartData, ListItem } from '@/app/mlops/types';
import { MetricItem, ThresholdField } from '@/app/mlops/types';
import { LEVEL_MAP } from '@/app/mlops/constants';

interface LineChartProps {
  data: ChartData[];
  unit?: string;
  metric?: MetricItem;
  threshold?: ThresholdField[];
  timeline?: any;
  showDimensionFilter?: boolean;
  showDimensionTable?: boolean;
  allowSelect?: boolean;
  showBrush?: boolean;
  onXRangeChange?: (arr: [Dayjs, Dayjs]) => void;
  onAnnotationClick?: (value: any) => void;
  onTimeLineChange?: (value: any) => void;
}

const getChartAreaKeys = (arr: ChartData[]): string[] => {
  const keys = new Set<string>();
  arr.forEach((obj) => {
    Object.keys(obj).forEach((key) => {
      if (key.includes('value')) {
        keys.add(key);
      }
    });
  });
  return Array.from(keys);
};

const getDetails = (arr: ChartData[]): Record<string, any> => {
  return arr.reduce((pre, cur) => {
    return Object.assign(pre, cur.details);
  }, {});
};

const LineChart: React.FC<LineChartProps> = ({
  data = [],
  unit = '',
  showDimensionFilter = false,
  metric = {},
  threshold = [],
  timeline = {
    startIndex: 0,
    endIndex: 0
  },
  allowSelect = true,
  showBrush = false,
  showDimensionTable = false,
  onXRangeChange,
  onTimeLineChange = () => { },
  onAnnotationClick = () => { },
}) => {
  const { formatTime } = useFormatTime();
  const [startX, setStartX] = useState<number | null>(null);
  const [endX, setEndX] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [colors, setColors] = useState<string[]>([]);
  const [visibleAreas, setVisibleAreas] = useState<string[]>([]);
  // 获取数据中的最小和最大时间
  const [minTime, maxTime] = useMemo(() => {
    if (!data.length) return [0, 0];
    const times = data.map(d => +new Date(d.timestamp));
    return [Math.min(...times), Math.max(...times)];
  }, [data]);

  // 优化事件处理函数，使用 useCallback 避免频繁重新创建
  const handleMouseDown = useCallback((e: any) => {
    if (!allowSelect) return;
    const activeLabel = e.activeLabel;
    if (activeLabel !== undefined) {
      setStartX(activeLabel);
      setIsDragging(true);
      document.body.style.userSelect = 'none';
    }
  }, [allowSelect]);

  const handleMouseMove = useCallback((e: any) => {
    if (!allowSelect || !isDragging) return;
    const activeLabel = e.activeLabel;
    if (activeLabel !== undefined) {
      setEndX(activeLabel);
    }
  }, [allowSelect, isDragging]);

  const handleMouseUp = useCallback(() => {
    if (!allowSelect) return;
    setIsDragging(false);
    document.body.style.userSelect = '';
    if (startX !== null && endX !== null) {
      const selectedTimeRange: [Dayjs, Dayjs] = [
        dayjs(Math.min(startX, endX) * 1000),
        dayjs(Math.max(startX, endX) * 1000),
      ];
      onXRangeChange && onXRangeChange(selectedTimeRange);
    }
    setStartX(null);
    setEndX(null);
  }, [allowSelect, startX, endX, onXRangeChange]);

  // 优化点击事件处理，减少数据处理开销
  const onClick = useCallback((data: any) => {
    if (!data?.activePayload) return;

    // 使用 requestAnimationFrame 延迟处理，避免阻塞渲染
    requestAnimationFrame(() => {
      const arr = data.activePayload.map((item: any) => item?.payload);
      onAnnotationClick(arr);
    });
  }, [onAnnotationClick]);

  // 优化渲染函数，使用 useCallback 避免重新创建
  const renderDot = useCallback((props: any) => {
    const { cx, cy, payload, index } = props;
    const { label } = payload;
    if (label === 1) {
      return <circle key={index} cx={cx} cy={cy} r={3.0} fill="red" />;
    }
    return <g key={index} />;
  }, []);

  const renderMinDot = useCallback((props: any) => {
    const { cx, cy, payload, index } = props;
    const { label } = payload;
    if (label === 1) {
      return <circle key={index} cx={cx} cy={cy} r={1} fill="red" />;
    }
    return <g key={index} />;
  }, []);


  // 添加防抖的 ref
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // 修复防抖逻辑
  const indexChange = useCallback((value: any) => {
    // 清除之前的定时器
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    // 设置新的定时器
    timeoutRef.current = setTimeout(() => {
      onTimeLineChange(value);
    }, 100); // 增加防抖时间到100ms，减少抖动
  }, [onTimeLineChange]);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  // 优化全局鼠标事件监听器，减少依赖项
  useEffect(() => {
    if (!allowSelect) return;

    const handleGlobalMouseUp = () => {
      if (isDragging) {
        handleMouseUp();
      }
    };

    window.addEventListener('mouseup', handleGlobalMouseUp);
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp);
    };
  }, [isDragging, handleMouseUp]);

  // 优化 renderYAxisTick，使用 useCallback
  const renderYAxisTick = useCallback((props: any) => {
    const { x, y, payload } = props;
    let label = String(payload.value);
    if (isStringArray(unit)) {
      const unitName = JSON.parse(unit).find(
        (item: ListItem) => item.id === +label
      )?.name;
      label = unitName || label;
    }
    const maxLength = 6;
    return (
      <text
        x={x}
        y={y}
        textAnchor="end"
        fontSize={14}
        fill="var(--color-text-3)"
        dy={4}
      >
        {label.length > maxLength && <title>{label}</title>}
        {label.length > maxLength
          ? `${label.slice(0, maxLength - 1)}...`
          : label}
      </text>
    );
  }, [unit]);

  // 优化 Brush 的 startIndex 和 endIndex 计算
  const brushStartIndex = useMemo(() => {
    return Math.max(0, Math.min(timeline.startIndex, Math.max(0, data.length - 1)));
  }, [timeline.startIndex, data.length]);

  const brushEndIndex = useMemo(() => {
    return Math.max(0, Math.min(timeline.endIndex, Math.max(0, data.length - 1)));
  }, [timeline.endIndex, data.length]);

  const chartKeys = useMemo(() => getChartAreaKeys(data), [data]);
  const chartDetails = useMemo(() => getDetails(data), [data]);

  useEffect(() => {

    setVisibleAreas(chartKeys);

    const generatedColors = chartKeys.map(() => generateUniqueRandomColor());
    setColors((prev: string[]) => {
      return [
        ...prev,
        ...generatedColors.slice(prev.length, generatedColors.length),
      ];
    });
  }, [data, chartKeys, chartDetails]);

  return (
    <div
      className={`flex w-full h-full ${showDimensionFilter || showDimensionTable ? 'flex-row' : 'flex-col'
      }`}
    >
      {!!data.length ? (
        <>
          <ResponsiveContainer className={chartLineStyle.chart}>
            <AreaChart
              data={data}
              margin={{
                top: 10,
                right: 0,
                left: 0,
                bottom: 0,
              }}
              onClick={onClick}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
            >
              <XAxis
                dataKey="timestamp"
                tick={{ fill: 'var(--color-text-3)', fontSize: 14 }}
                tickFormatter={(tick) => formatTime(tick, minTime, maxTime)}
              />
              <YAxis axisLine={false} tickLine={false} tick={renderYAxisTick} />

              {threshold.map((item, index) => {
                return (
                  <ReferenceLine
                    key={index}
                    y={`${item.value}`}
                    isFront
                    stroke={`${LEVEL_MAP[item.level]}`}
                    strokeDasharray="12 3 3 3 3 3"
                  >
                    <Label
                      value={`${item.value}`}
                      fill={`${LEVEL_MAP[item.level]}`}
                      position="left"
                      dx={30}
                      dy={-10}
                    ></Label>
                  </ReferenceLine>
                );
              })}
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <Tooltip
                offset={15}
                content={
                  <CustomTooltip
                    unit={unit}
                    visible={!isDragging}
                    metric={metric as MetricItem}
                  />
                }
              />
              {chartKeys.map((key, index) => (
                <Area
                  key={index}
                  type="monotone"
                  dataKey={key}
                  dot={renderDot}
                  stroke={'#1976d2'}
                  strokeWidth={2}
                  fillOpacity={0}
                  fill={colors[index]}
                  hide={!visibleAreas.includes(key)}
                  isAnimationActive={false}
                />
              ))}
              {isDragging &&
                startX !== null &&
                endX !== null &&
                allowSelect && (
                <ReferenceArea
                  x1={Math.min(startX, endX)}
                  x2={Math.max(startX, endX)}
                  strokeOpacity={0.3}
                  fill="rgba(0, 0, 255, 0.1)"
                />
              )}
              {showBrush && 
                <Brush
                  dataKey="timestamp"
                  height={30}
                  travellerWidth={5}
                  stroke="#8884d8"
                  fill={`var(--color-bg-1)`}
                  startIndex={brushStartIndex}
                  endIndex={brushEndIndex}
                  onChange={indexChange}
                  tickFormatter={(tick) => formatTime(tick, minTime, maxTime)}
                >
                  <AreaChart data={data}>
                    {chartKeys.map((key, index) => (
                      <Area
                        key={key}
                        type="monotone"
                        dataKey={key}
                        stroke={'#1976d2'}
                        fill={colors[index]}
                        fillOpacity={0}
                        isAnimationActive={false}
                        dot={renderMinDot}
                      />
                    ))}
                  </AreaChart>
                </Brush>
              }
            </AreaChart>
          </ResponsiveContainer>
        </>
      ) : (
        <div className={`${chartLineStyle.chart} ${chartLineStyle.noData}`}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </div>
      )}
    </div>
  );
};

export default LineChart;
