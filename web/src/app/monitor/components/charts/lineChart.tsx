import React, {
  useState,
  useEffect,
  useMemo,
  useCallback,
  memo,
  useRef,
  useId
} from 'react';
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
  ReferenceLine
} from 'recharts';
import CustomTooltip from './customTooltips';
import EventBar from './eventBar';
import {
  useFormatTime,
  isStringArray
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
  ThresholdField
} from '@/app/monitor/types';
import { LEVEL_MAP } from '@/app/monitor/constants';
import { useLevelList } from '@/app/monitor/hooks';
import {
  GAP_INTERVAL_AREA_STYLE,
  getChartDataWithGapBreaks,
  getRenderedGapIntervals
} from '@/app/monitor/utils/gapIntervals';

// 折线图固定分类色板（AntV/G2，跨图表统一）。按序列索引稳定分配，
// 替代随机配色，保证同一序列跨刷新/跨视图颜色稳定、彼此可区分。
const CHART_PALETTE = [
  '#5B8FF9', '#5AD8A6', '#F6BD16', '#E86452', '#6DC8EC',
  '#945FB9', '#FF9845', '#1E9493'
];
// 折线图默认视觉 token（报告风）：细线 + linear 折角 + 渐变淡填充
const DEFAULT_STROKE_WIDTH = 1;
const DEFAULT_FILL_OPACITY = 0.36;

interface LineChartProps {
  data: ChartData[];
  unit?: string;
  metric?: MetricItem;
  threshold?: ThresholdField[];
  eventData?: TableDataItem[];
  showDimensionFilter?: boolean;
  showDimensionTable?: boolean;
  allowSelect?: boolean;
  syncId?: string;
  onXRangeChange?: (arr: [Dayjs, Dayjs]) => void;
  seriesStyles?: Array<{
    color?: string;
    strokeDasharray?: string;
    fillOpacity?: number;
    strokeOpacity?: number;
    strokeWidth?: number;
    unit?: string;
  }>;
  xAxisTimeFormat?: string;
  leftAxisWidthOverride?: number;
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

interface ResolvedSeriesStyle {
  color: string;
  strokeDasharray?: string;
  fillOpacity: number;
  strokeOpacity: number;
  strokeWidth: number;
  unit?: string;
}

const getNiceStep = (rawStep: number) => {
  if (!Number.isFinite(rawStep) || rawStep <= 0) {
    return 1;
  }

  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;

  if (normalized <= 1) return magnitude;
  if (normalized <= 2) return 2 * magnitude;
  if (normalized <= 5) return 5 * magnitude;
  return 10 * magnitude;
};

const formatAxisNumber = (value: number) => {
  if (!Number.isFinite(value)) {
    return '';
  }

  if (Math.abs(value) >= 1000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  if (Number.isInteger(value)) {
    return `${value}`;
  }

  return value.toFixed(2).replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1');
};

const buildNiceAxis = (
  rawDomain: [number | 'auto', number | 'auto'],
  tickCount: number
) => {
  const [rawMin, rawMax] = rawDomain;
  const minValue = typeof rawMin === 'number' ? rawMin : 0;
  const maxValue = typeof rawMax === 'number' ? rawMax : minValue + 1;
  const span = Math.max(maxValue - minValue, 1e-6);
  const step = getNiceStep(span / Math.max(tickCount - 1, 1));

  let niceMin = Math.floor(minValue / step) * step;
  let niceMax = Math.ceil(maxValue / step) * step;

  if (minValue >= 0) {
    niceMin = Math.max(0, niceMin);
  }

  if (niceMax <= niceMin) {
    niceMax = niceMin + step;
  }

  const ticks: number[] = [];
  for (let current = niceMin; current <= niceMax + step / 2; current += step) {
    ticks.push(Number(current.toFixed(10)));
  }

  return {
    domain: [niceMin, niceMax] as [number, number],
    ticks
  };
};

const LineChart: React.FC<LineChartProps> = memo(
  ({
    data,
    unit = '',
    showDimensionFilter = false,
    metric,
    threshold = [],
    eventData = [],
    allowSelect = true,
    showDimensionTable = false,
    syncId,
    onXRangeChange,
    seriesStyles = [],
    xAxisTimeFormat,
    leftAxisWidthOverride
  }) => {
    const { formatTime } = useFormatTime();
    const levelList = useLevelList();
    const [startX, setStartX] = useState<number | null>(null);
    const [endX, setEndX] = useState<number | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [visibleAreas, setVisibleAreas] = useState<string[]>([]);
    const gradientId = useId().replace(/:/g, '');
    const [hoveredThreshold, setHoveredThreshold] =
      useState<ThresholdField | null>(null);
    const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
    const containerRef = useRef<HTMLDivElement>(null);
    const [containerHeight, setContainerHeight] = useState<number>(0);
    const [containerWidth, setContainerWidth] = useState<number>(0);

    // 监听容器尺寸变化
    useEffect(() => {
      const updateSize = () => {
        if (containerRef.current) {
          setContainerHeight(containerRef.current.clientHeight);
          setContainerWidth(containerRef.current.clientWidth);
        }
      };
      updateSize();
      window.addEventListener('resize', updateSize);
      return () => window.removeEventListener('resize', updateSize);
    }, []);

    const chartAreaKeys = useMemo(() => getChartAreaKeys(data), [data]);

    const details = useMemo(() => getDetails(data), [data]);

    const resolvedSeriesStyles = useMemo<ResolvedSeriesStyle[]>(
      () =>
        chartAreaKeys.map((_, index) => ({
          color:
            seriesStyles[index]?.color ||
            (index === 0 && metric && typeof metric.color === 'string' ? metric.color : '') ||
            CHART_PALETTE[index % CHART_PALETTE.length],
          strokeDasharray: seriesStyles[index]?.strokeDasharray,
          fillOpacity: seriesStyles[index]?.fillOpacity ?? DEFAULT_FILL_OPACITY,
          strokeOpacity: seriesStyles[index]?.strokeOpacity ?? 1,
          strokeWidth: seriesStyles[index]?.strokeWidth ?? DEFAULT_STROKE_WIDTH,
          unit: seriesStyles[index]?.unit
        })),
      [chartAreaKeys, metric, seriesStyles]
    );

    const seriesUnits = useMemo(
      () => Object.fromEntries(chartAreaKeys.map((key, index) => [key, resolvedSeriesStyles[index]?.unit || unit])),
      [chartAreaKeys, resolvedSeriesStyles, unit]
    );

    const renderedGapIntervals = useMemo(
      () => getRenderedGapIntervals(data, data[0]?.gapIntervals || []),
      [data]
    );

    const chartDataWithGapBreaks = useMemo(
      () => getChartDataWithGapBreaks(data, data[0]?.gapIntervals || []),
      [data]
    );

    const yAxisTickCount = useMemo(() => {
      if (containerHeight && containerHeight <= 220) {
        return 3;
      }

      return 4;
    }, [containerHeight]);

    const visibleColors = useMemo<string[]>(() => resolvedSeriesStyles.map((item) => item.color), [resolvedSeriesStyles]);

    const xAxisTickCount = useMemo(() => {
      if (containerWidth >= 1400) {
        return 7;
      }

      if (containerWidth >= 1100) {
        return 6;
      }

      if (containerWidth >= 800) {
        return 5;
      }

      return 4;
    }, [containerWidth]);

    const levelNameMap = useMemo(() => {
      return levelList.reduce(
        (acc, item) => {
          if (item.value) {
            acc[item.value as string] = item.label || '';
          }
          return acc;
        },
        {} as Record<string, string>
      );
    }, [levelList]);

    // 格式化数值：固定最大宽度，超出显示省略号
    const formatThresholdValue = useCallback((num: number): string => {
      const MAX_LENGTH = 6; // 数值最大显示长度，超过5位数才显示省略号
      const str = String(num);
      if (str.length <= MAX_LENGTH) {
        return str;
      }
      return str.slice(0, MAX_LENGTH - 1) + '…';
    }, []);

    const { minTime, maxTime } = useMemo(() => {
      const times = data.map((d) => d.time);
      return {
        minTime: +new Date(Math.min(...times)),
        maxTime: +new Date(Math.max(...times))
      };
    }, [data]);

    // 计算 Y 轴范围，确保阈值线能显示
    const yAxisDomain = useMemo((): [number | 'auto', number | 'auto'] => {
      // 获取数据中的所有值
      const dataValues: number[] = [];
      data.forEach((item) => {
        chartAreaKeys.forEach((key) => {
          const val = item[key];
          if (typeof val === 'number' && !isNaN(val)) {
            dataValues.push(val);
          }
        });
      });

      if (!dataValues.length && !threshold.length) {
        return [0, 'auto'];
      }

      const dataMin = dataValues.length ? Math.min(...dataValues) : 0;
      const dataMax = dataValues.length ? Math.max(...dataValues) : 0;
      const dataSpan = dataMax - dataMin;
      const basePadding = dataSpan > 0
        ? dataSpan * 0.12
        : Math.max(Math.abs(dataMax || dataMin) * 0.18, 0.6);
      let yMin = dataMin - basePadding;
      let yMax = dataMax + basePadding;

      if (dataValues.length && dataMin >= 0) {
        yMin = Math.max(0, yMin);
      }

      if (dataValues.length && dataSpan === 0) {
        if (dataMax === 0) {
          yMax = 1;
        } else {
          yMin = Math.max(dataMin >= 0 ? 0 : dataMin - basePadding, dataMin - basePadding);
          yMax = dataMax + basePadding;
        }
      }

      if (!threshold.length) {
        return [yMin, yMax];
      }

      // 获取所有有效阈值
      const validThresholdItems = threshold.filter(
        (item) => item.value !== null && item.value !== undefined
      );
      const thresholdValues = validThresholdItems.map(
        (item) => item.value as number
      );
      // 如果没有数据或阈值，返回自动计算
      if (!thresholdValues.length) {
        return [yMin, yMax];
      }
      const thresholdMax = Math.max(...thresholdValues);
      const thresholdMin = Math.min(...thresholdValues);

      // 检查是否有"大于"类型的阈值（需要向上显示阴影区域）
      const hasGreaterThan = validThresholdItems.some(
        (item) => item.method === '>' || item.method === '>=' || !item.method
      );

      if (thresholdMin < yMin) {
        yMin = thresholdMin;
      }

      if (thresholdMax > yMax) {
        yMax = hasGreaterThan ? Math.ceil(thresholdMax * 1.1) : thresholdMax;
      }

      if (yMin >= 0) {
        yMin = Math.max(0, yMin);
      }

      return [yMin, yMax];
    }, [data, chartAreaKeys, threshold]);

    const niceYAxis = useMemo(() => buildNiceAxis(yAxisDomain, yAxisTickCount), [yAxisDomain, yAxisTickCount]);

    const leftAxisWidth = useMemo(() => {
      if (typeof leftAxisWidthOverride === 'number') {
        return leftAxisWidthOverride;
      }

      if (isStringArray(unit)) {
        return 56;
      }

      const maxLabelLength = Math.max(
        ...niceYAxis.ticks.map((tick) => formatAxisNumber(Number(tick)).length),
        1
      );

      return Math.min(Math.max(maxLabelLength * 8 + 8, 32), 50);
    }, [leftAxisWidthOverride, niceYAxis.ticks, unit]);

    // 计算阈值标签信息（包含格式化文本和偏移量）
    const thresholdLabelInfo = useMemo(() => {
      const validItems = threshold
        .filter((item) => item.value !== null && item.value !== undefined)
        .map((item) => ({
          ...item,
          numValue: item.value as number,
          formattedValue: formatThresholdValue(item.value as number),
          labelText: `${levelNameMap[item.level] || item.level} ${formatThresholdValue(item.value as number)}`,
          // 使用 level + value 作为唯一标识
          uniqueKey: `${item.level}_${item.value}`
        }))
        .sort((a, b) => b.numValue - a.numValue); // 按值从大到小排序

      // 计算 Y 轴像素高度（估算，减去上下边距）
      const chartHeight = (containerHeight || 300) - 40;
      const yMin = niceYAxis.domain[0];
      const yMax =
        niceYAxis.domain[1] || Math.max(...validItems.map((i) => i.numValue), 1);
      const yRange = yMax - yMin || 1;

      // 为每个标签计算 dy 偏移量，避免重叠
      const LABEL_HEIGHT = 16; // 标签高度
      const MIN_LABEL_DISTANCE = LABEL_HEIGHT + 4; // 最小标签间距（像素）
      const BOTTOM_LIMIT = chartHeight - 10; // 底部限制，避免与X轴重叠
      const TOP_LIMIT = 5; // 顶部限制，避免被裁剪

      // 使用 uniqueKey 作为键存储偏移量
      const labelOffsets: Record<string, number> = {};
      // 记录每个标签的最终渲染 Y 位置（从顶部算起的像素）
      const finalPositions: number[] = [];
      // 记录每个标签的原始 Y 位置
      const originalPositions: number[] = [];

      // 第一步：计算每个标签的原始位置
      for (let i = 0; i < validItems.length; i++) {
        const current = validItems[i];
        const currentYPixel =
          ((yMax - current.numValue) / yRange) * chartHeight;
        originalPositions.push(currentYPixel);
        finalPositions.push(currentYPixel); // 初始化为原始位置
      }

      // 第二步：从下往上处理，检查是否压着X轴或重叠
      for (let i = validItems.length - 1; i >= 0; i--) {
        let currentY = finalPositions[i];

        // 检查是否超出底部限制（压着X轴）
        if (currentY > BOTTOM_LIMIT) {
          currentY = BOTTOM_LIMIT;
          finalPositions[i] = currentY;
        }

        // 检查是否与下一个标签重叠（下一个标签在下方，索引更大）
        if (i < validItems.length - 1) {
          const nextY = finalPositions[i + 1];
          const distance = nextY - currentY;

          if (distance < MIN_LABEL_DISTANCE) {
            // 重叠了，当前标签需要往上移
            currentY = nextY - MIN_LABEL_DISTANCE;
            finalPositions[i] = currentY;
          }
        }

        // 检查是否超出顶部限制
        if (currentY < TOP_LIMIT) {
          currentY = TOP_LIMIT;
          finalPositions[i] = currentY;
        }
      }

      // 第三步：从上往下再检查一次，确保顶部标签被限制后，下面的标签也正确排列
      for (let i = 1; i < validItems.length; i++) {
        const prevY = finalPositions[i - 1];
        let currentY = finalPositions[i];

        // 检查是否与上一个标签重叠
        const distance = currentY - prevY;
        if (distance < MIN_LABEL_DISTANCE) {
          currentY = prevY + MIN_LABEL_DISTANCE;
          finalPositions[i] = currentY;
        }
      }

      // 第四步：计算偏移量
      for (let i = 0; i < validItems.length; i++) {
        const current = validItems[i];
        labelOffsets[current.uniqueKey] =
          finalPositions[i] - originalPositions[i];
      }

      return {
        items: validItems,
        labelOffsets,
        maxLabelLength: Math.max(
          ...validItems.map((i) => i.labelText.length),
          0
        )
      };
    }, [
      threshold,
      levelNameMap,
      formatThresholdValue,
      containerHeight,
      niceYAxis
    ]);

    // 计算右侧 margin：级别名称动态 + 数值动态（有最大宽度限制）
    const rightMargin = useMemo(() => {
      if (!threshold?.length) {
        return eventData?.length ? 20 : 0;
      }
      const validItems = threshold.filter(
        (item) => item.value !== null && item.value !== undefined
      );
      // 获取最长的级别名称长度
      const maxLevelNameLength = Math.max(
        ...validItems.map(
          (item) => (levelNameMap[item.level] || item.level).length
        ),
        0
      );
      // 获取格式化后的数值最大长度（最多 6 个字符）
      const maxValueLength = Math.max(
        ...validItems.map(
          (item) => formatThresholdValue(item.value as number).length
        ),
        0
      );
      // 级别名称宽度（中文字符约 12px）+ 数值宽度（数字约 8px）+ 间距
      const levelNameWidth = maxLevelNameLength * 12;
      const valueWidth = maxValueLength * 8;
      const padding = 15;
      return levelNameWidth + valueWidth + padding;
    }, [threshold, eventData?.length, levelNameMap, formatThresholdValue]);

    // 获取所有有效的阈值配置，用于渲染阴影区域
    const validThresholds = useMemo(() => {
      return threshold
        .filter((item) => item.value !== null && item.value !== undefined)
        .map((item) => ({
          level: item.level,
          value: item.value as number,
          method: item.method || '>'
        }));
    }, [threshold]);

    const hasDimension = useMemo(() => {
      return !Object.values(details || {}).every((item) => !item.length);
    }, [details]);

    // 默认展示全部序列
    useEffect(() => {
      setVisibleAreas(chartAreaKeys);
    }, [chartAreaKeys]);

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
        if (typeof e?.activeLabel !== 'number') return;
        setStartX(e.activeLabel);
        setEndX(null);
        setIsDragging(true);
        document.body.style.userSelect = 'none'; // 禁用文本选择
      },
      [allowSelect]
    );

    const handleMouseMove = useCallback(
      (e: any) => {
        if (!allowSelect) return;
        if (isDragging) {
          if (typeof e?.activeLabel !== 'number') return;
          setEndX(e.activeLabel);
        }
      },
      [allowSelect, isDragging]
    );

    const handleMouseUp = useCallback(() => {
      if (!allowSelect) return;
      setIsDragging(false);
      document.body.style.userSelect = ''; // 重新启用文本选择
      if (typeof startX === 'number' && typeof endX === 'number' && startX !== endX) {
        const selectedTimeRange: [Dayjs, Dayjs] = [
          dayjs(Math.min(startX, endX) * 1000),
          dayjs(Math.max(startX, endX) * 1000)
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
        } else {
          label = formatAxisNumber(Number(payload.value));
        }
        const maxLength = 6; // 设置标签的最大长度
        return (
          <text
            x={x}
            y={y}
            textAnchor="end"
            fontSize={12}
            fill="var(--color-text-3)"
            dy={4}
            dx={2}
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

    const formatXAxisTick = useCallback(
      (tick: number) => {
        if (xAxisTimeFormat) {
          return dayjs(tick * 1000).format(xAxisTimeFormat);
        }

        return formatTime(tick, minTime, maxTime);
      },
      [formatTime, maxTime, minTime, xAxisTimeFormat]
    );

    return (
      <div
        ref={containerRef}
        className={`flex w-full h-full ${
          showDimensionFilter || showDimensionTable ? 'flex-row' : 'flex-col'
        }`}
      >
        {!!data.length ? (
          <>
            <ResponsiveContainer className={chartLineStyle.chart}>
              <AreaChart
                data={chartDataWithGapBreaks}
                syncId={syncId}
                margin={{
                  top: 10,
                  right: rightMargin,
                  left: 0,
                  bottom: 6
                }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
              >
                <XAxis
                  dataKey="time"
                  type="number"
                  domain={['dataMin', 'dataMax']}
                  tick={{ fill: 'var(--color-text-3)', fontSize: 12 }}
                  tickFormatter={formatXAxisTick}
                  tickCount={xAxisTickCount}
                  minTickGap={36}
                  dy={8}
                />
                <YAxis
                  yAxisId="left"
                  axisLine={false}
                  tickLine={false}
                  tick={renderYAxisTick}
                  domain={niceYAxis.domain}
                  allowDataOverflow={false}
                  ticks={niceYAxis.ticks}
                  interval={0}
                  width={leftAxisWidth}
                />
                <CartesianGrid vertical={false} stroke="var(--color-border-1)" />
                {renderedGapIntervals.map((gap) => (
                  <ReferenceArea
                    key={`gap-${gap.start}-${gap.end}`}
                    x1={gap.start}
                    x2={gap.end}
                    yAxisId="left"
                    {...GAP_INTERVAL_AREA_STYLE}
                    ifOverflow="extendDomain"
                  />
                ))}
                <Tooltip
                  offset={-1}
                  cursor={{
                    stroke: 'var(--color-text-3)',
                    strokeWidth: 1,
                    strokeDasharray: '3 3'
                  }}
                  content={
                    <CustomTooltip
                      unit={unit}
                      visible={!isDragging}
                      metric={metric as MetricItem}
                      seriesUnits={seriesUnits}
                      maxHeight={
                        containerHeight ? containerHeight * 0.75 : undefined
                      }
                      maxWidth={
                        containerWidth ? containerWidth * 0.8 : undefined
                      }
                    />
                  }
                />
                {/* 每条序列的渐变填充：顶部为该序列色（透明度=fillOpacity），底部淡出 */}
                <defs>
                  {chartAreaKeys.map((key, index) => {
                    const color = resolvedSeriesStyles[index]?.color;
                    const fillOpacity =
                      resolvedSeriesStyles[index]?.fillOpacity ?? DEFAULT_FILL_OPACITY;
                    return (
                      <linearGradient
                        key={`grad-${key}`}
                        id={`${gradientId}-${index}`}
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop offset="0%" stopColor={color} stopOpacity={fillOpacity} />
                        <stop offset="100%" stopColor={color} stopOpacity={0} />
                      </linearGradient>
                    );
                  })}
                </defs>
                {chartAreaKeys.map((key, index) => (
                    <Area
                      key={key}
                      type="linear"
                      dataKey={key}
                      yAxisId="left"
                      stroke={resolvedSeriesStyles[index]?.color}
                      strokeDasharray={resolvedSeriesStyles[index]?.strokeDasharray}
                      strokeOpacity={resolvedSeriesStyles[index]?.strokeOpacity}
                    fillOpacity={1}
                    fill={`url(#${gradientId}-${index})`}
                    strokeWidth={resolvedSeriesStyles[index]?.strokeWidth ?? DEFAULT_STROKE_WIDTH}
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 2, fill: resolvedSeriesStyles[index]?.color }}
                    isAnimationActive={false}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    hide={!visibleAreas.includes(key)}
                  />
                ))}
                {/* 为每个阈值级别渲染阴影区域 */}
                {validThresholds.map((item, index) => {
                  const levelColor =
                    (LEVEL_MAP[item.level] as string) || '#F43B2C';
                  // 将颜色转换为 rgba 格式，透明度 0.1
                  const fillColor = levelColor.startsWith('#')
                    ? `rgba(${parseInt(levelColor.slice(1, 3), 16)}, ${parseInt(levelColor.slice(3, 5), 16)}, ${parseInt(levelColor.slice(5, 7), 16)}, 0.1)`
                    : levelColor;

                  const yMax = niceYAxis.domain[1];

                  // = 等于：不显示阴影区域（只显示阈值线）
                  if (item.method === '=') {
                    return null;
                  }

                  // != 不等于：显示全部区域（0 到最大值）
                  if (item.method === '!=') {
                    return (
                      <ReferenceArea
                        key={`area-${item.level}-${index}`}
                        yAxisId="left"
                        y1={0}
                        y2={yMax}
                        fill={fillColor}
                        fillOpacity={1}
                      />
                    );
                  }

                  // < 或 <= ：从 0 到阈值
                  const isLessThan =
                    item.method === '<' || item.method === '<=';

                  return (
                    <ReferenceArea
                      key={`area-${item.level}-${index}`}
                      yAxisId="left"
                      y1={isLessThan ? 0 : item.value}
                      y2={isLessThan ? item.value : yMax}
                      fill={fillColor}
                      fillOpacity={1}
                    />
                  );
                })}
                {/* 阈值线的鼠标触发区域（透明，较粗） */}
                {threshold.map((item, index) => (
                  <ReferenceLine
                    key={`trigger-${index}`}
                    y={`${item.value}`}
                    yAxisId="left"
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

                {/* 阈值线的可视部分（实线），使用排序后的列表确保正确的偏移计算 */}
                {thresholdLabelInfo.items.map((item) => {
                  const formattedValue = item.formattedValue;
                  const originalValue = String(item.numValue);
                  const levelColor =
                    (LEVEL_MAP[item.level] as string) || '#F43B2C';
                  const fullText = `${levelNameMap[item.level] || item.level} ${originalValue}`;
                  // 使用 uniqueKey 获取偏移量
                  const dy =
                    thresholdLabelInfo.labelOffsets[item.uniqueKey] || 0;

                  return (
                    <ReferenceLine
                      key={`visual-${item.uniqueKey}`}
                      y={`${item.numValue}`}
                      yAxisId="left"
                      isFront={true}
                      stroke={levelColor}
                      strokeWidth={1}
                      style={{ pointerEvents: 'none' }}
                      label={({ viewBox }) => {
                        const vb = viewBox as {
                          x: number;
                          y: number;
                          width: number;
                          height: number;
                        };
                        const levelName =
                          levelNameMap[item.level] || item.level;
                        return (
                          <text
                            x={vb.x + vb.width + 4}
                            y={vb.y}
                            dy={dy}
                            fill={levelColor}
                            fontSize={12}
                            dominantBaseline="middle"
                          >
                            <title>{fullText}</title>
                            <tspan>{levelName}</tspan>
                            <tspan dx={2}>{formattedValue}</tspan>
                          </text>
                        );
                      }}
                    />
                  );
                })}

                {isDragging &&
                  startX !== null &&
                  endX !== null &&
                  allowSelect && (
                  <ReferenceArea
                    x1={Math.min(startX, endX)}
                    x2={Math.max(startX, endX)}
                    yAxisId="left"
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
                colors={visibleColors}
                visibleAreas={visibleAreas}
                details={details}
                onLegendClick={handleLegendClick}
              />
            )}
            {showDimensionTable && hasDimension && (
              <DimensionTable
                data={data}
                colors={visibleColors}
                details={details}
                unit={unit}
              />
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
                  whiteSpace: 'nowrap'
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
