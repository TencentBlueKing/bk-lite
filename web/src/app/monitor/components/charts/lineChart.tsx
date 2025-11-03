import React, { useState, useEffect, useMemo, useCallback, memo } from 'react';
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
} from 'recharts';
import CustomTooltip from './customTooltips';
import EventBar from './eventBar';
import {
  generateUniqueRandomColor,
  useFormatTime,
  isStringArray,
} from '@/app/monitor/utils/common';
import chartLineStyle from './index.module.scss';
import dayjs, { Dayjs } from 'dayjs';
import DimensionFilter from './dimensionFilter';
import DimensionTable from './dimensionTable';
import {
  ChartData,
  ListItem,
  TableDataItem,
  MetricItem,
  ThresholdField,
} from '@/app/monitor/types';
import { LEVEL_MAP } from '@/app/monitor/constants';

interface LineChartProps {
  data: ChartData[];
  unit?: string;
  metric?: MetricItem;
  threshold?: ThresholdField[];
  eventData?: TableDataItem[];
  showDimensionFilter?: boolean;
  showDimensionTable?: boolean;
  allowSelect?: boolean;
  onXRangeChange?: (arr: [Dayjs, Dayjs]) => void;
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

const LineChart: React.FC<LineChartProps> = memo(
  ({
    data,
    unit = '',
    showDimensionFilter = false,
    metric = {},
    threshold = [],
    eventData = [],
    allowSelect = true,
    showDimensionTable = false,
    onXRangeChange,
  }) => {
    const { formatTime } = useFormatTime();
    const [startX, setStartX] = useState<number | null>(null);
    const [endX, setEndX] = useState<number | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [colors, setColors] = useState<string[]>([]);
    const [visibleAreas, setVisibleAreas] = useState<string[]>([]);
    const [hoveredThreshold, setHoveredThreshold] =
      useState<ThresholdField | null>(null);
    const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });

    const chartAreaKeys = useMemo(() => getChartAreaKeys(data), [data]);

    const details = useMemo(() => getDetails(data), [data]);

    const { minTime, maxTime } = useMemo(() => {
      const times = data.map((d) => d.time);
      return {
        minTime: +new Date(Math.min(...times)),
        maxTime: +new Date(Math.max(...times)),
      };
    }, [data]);

    const hasDimension = useMemo(() => {
      return !Object.values(details || {}).every((item) => !item.length);
    }, [details]);

    // 生成颜色的逻辑优化
    useEffect(() => {
      if (chartAreaKeys.length > colors.length) {
        const newColors = Array.from(
          { length: chartAreaKeys.length - colors.length },
          () => generateUniqueRandomColor()
        );
        setColors((prev) => [...prev, ...newColors]);
      }
      setVisibleAreas(chartAreaKeys);
    }, [chartAreaKeys, colors.length]);

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
    }, [isDragging, startX, endX]);

    const handleMouseDown = useCallback(
      (e: any) => {
        if (!allowSelect) return;
        setStartX((pre) => e.activeLabel || pre);
        setIsDragging(true);
        document.body.style.userSelect = 'none'; // 禁用文本选择
      },
      [allowSelect]
    );

    const handleMouseMove = useCallback(
      (e: any) => {
        if (!allowSelect) return;
        if (isDragging) {
          setEndX((pre) => e.activeLabel || pre);
        }
      },
      [allowSelect, isDragging]
    );

    const handleMouseUp = useCallback(() => {
      if (!allowSelect) return;
      setIsDragging(false);
      document.body.style.userSelect = ''; // 重新启用文本选择
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

    const handleLegendClick = useCallback((key: string) => {
      setVisibleAreas((prevVisibleAreas) =>
        prevVisibleAreas.includes(key)
          ? prevVisibleAreas.filter((area) => area !== key)
          : [...prevVisibleAreas, key]
      );
    }, []);

    const renderYAxisTick = useCallback(
      (props: any) => {
        const { x, y, payload } = props;
        let label = String(payload.value);
        if (isStringArray(unit)) {
          const unitName = JSON.parse(unit).find(
            (item: ListItem) => item.id === +label
          )?.name;
          label = unitName || label;
        }
        const maxLength = 6; // 设置标签的最大长度
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
      },
      [unit]
    );

    return (
      <div
        className={`flex w-full h-full ${
          showDimensionFilter || showDimensionTable ? 'flex-row' : 'flex-col'
        }`}
      >
        {!!data.length ? (
          <>
            <ResponsiveContainer className={chartLineStyle.chart}>
              <AreaChart
                data={data}
                margin={{
                  top: 10,
                  right: eventData?.length ? 20 : 0,
                  left: 0,
                  bottom: 0,
                }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
              >
                <XAxis
                  dataKey="time"
                  tick={{ fill: 'var(--color-text-3)', fontSize: 14 }}
                  tickFormatter={(tick) => formatTime(tick, minTime, maxTime)}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={renderYAxisTick}
                />

                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <Tooltip
                  offset={20}
                  content={
                    <CustomTooltip
                      unit={unit}
                      visible={!isDragging}
                      metric={metric as MetricItem}
                    />
                  }
                />
                {chartAreaKeys.map((key, index) => (
                  <Area
                    key={key}
                    type="monotone"
                    dataKey={key}
                    stroke={colors[index]}
                    fillOpacity={0}
                    fill={colors[index]}
                    hide={!visibleAreas.includes(key)}
                  />
                ))}
                {/* 阈值线的鼠标触发区域（透明，较粗） */}
                {threshold.map((item, index) => (
                  <ReferenceLine
                    key={`trigger-${index}`}
                    y={`${item.value}`}
                    isFront={true}
                    stroke="transparent"
                    strokeWidth={8}
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={(e) => {
                      setHoveredThreshold(item);
                      setMousePosition({ x: e.clientX, y: e.clientY });
                    }}
                    onMouseLeave={() => {
                      setHoveredThreshold(null);
                    }}
                    onMouseMove={(e) => {
                      setMousePosition({ x: e.clientX, y: e.clientY });
                    }}
                  />
                ))}

                {/* 阈值线的可视部分（较细） */}
                {threshold.map((item, index) => (
                  <ReferenceLine
                    key={`visual-${index}`}
                    y={`${item.value}`}
                    isFront={true}
                    stroke={`${LEVEL_MAP[item.level]}`}
                    strokeDasharray="12 3 3 3 3 3"
                    strokeWidth={2}
                    style={{ pointerEvents: 'none' }}
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
              </AreaChart>
            </ResponsiveContainer>

            <EventBar
              eventData={eventData}
              minTime={minTime}
              maxTime={maxTime}
            />

            {showDimensionFilter && hasDimension && (
              <DimensionFilter
                data={data}
                colors={colors}
                visibleAreas={visibleAreas}
                details={details}
                onLegendClick={handleLegendClick}
              />
            )}
            {showDimensionTable && hasDimension && (
              <DimensionTable data={data} colors={colors} details={details} />
            )}

            {/* 自定义阈值tooltip */}
            {hoveredThreshold && (
              <div
                style={{
                  position: 'fixed',
                  left: mousePosition.x + 10,
                  top: mousePosition.y - 10,
                  background: 'rgba(0, 0, 0, 0.8)',
                  color: 'white',
                  padding: '8px 12px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  pointerEvents: 'none',
                  zIndex: 1000,
                  whiteSpace: 'nowrap',
                }}
              >
                {hoveredThreshold.value}
              </div>
            )}
          </>
        ) : (
          <div className={`${chartLineStyle.chart} ${chartLineStyle.noData}`}>
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        )}
      </div>
    );
  }
);

LineChart.displayName = 'LineChart';

export default LineChart;
