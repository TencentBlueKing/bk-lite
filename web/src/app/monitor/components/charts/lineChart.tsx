import React, {
  useState,
  useEffect,
  useMemo,
  useCallback,
  memo,
  useRef
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
  generateUniqueRandomColor,
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
    onXRangeChange
  }) => {
    const { formatTime } = useFormatTime();
    const levelList = useLevelList();
    const [startX, setStartX] = useState<number | null>(null);
    const [endX, setEndX] = useState<number | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [colors, setColors] = useState<string[]>([]);
    const [visibleAreas, setVisibleAreas] = useState<string[]>([]);
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
      if (!threshold.length) {
        return [0, 'auto'];
      }
      // 获取数据中的所有值
      const dataValues: number[] = [];
      data.forEach((item) => {
        Object.keys(item).forEach((key) => {
          if (key.includes('value')) {
            const val = item[key];
            if (typeof val === 'number' && !isNaN(val)) {
              dataValues.push(val);
            }
          }
        });
      });
      // 获取所有有效阈值
      const validThresholdItems = threshold.filter(
        (item) => item.value !== null && item.value !== undefined
      );
      const thresholdValues = validThresholdItems.map(
        (item) => item.value as number
      );
      // 如果没有数据或阈值，返回自动计算
      if (!dataValues.length || !thresholdValues.length) {
        return [0, 'auto'];
      }
      const dataMax = Math.max(...dataValues);
      const thresholdMax = Math.max(...thresholdValues);

      // 检查是否有"大于"类型的阈值（需要向上显示阴影区域）
      const hasGreaterThan = validThresholdItems.some(
        (item) => item.method === '>' || item.method === '>=' || !item.method
      );

      // 只有当阈值最大值超过数据最大值时，才用阈值最大值设置 Y 轴上限
      if (thresholdMax > dataMax) {
        // 如果有"大于"类型的阈值，需要额外留出空间显示阴影区域
        const yMax = hasGreaterThan
          ? Math.ceil(thresholdMax * 1.1)
          : thresholdMax;
        return [0, yMax];
      }
      return [0, 'auto'];
    }, [data, threshold]);

    // 计算阈值标签信息（包含格式化文本和偏移量）
    const thresholdLabelInfo = useMemo(() => {
      const validItems = threshold
        .filter((item) => item.value !== null && item.value !== undefined)
        .map((item) => ({
          ...item,
          numValue: item.value as number,
          formattedValue: formatThresholdValue(item.value as number),
          labelText: `${levelNameMap[item.level] || item.level} ${formatThresholdValue(item.value as number)}`
        }))
        .sort((a, b) => b.numValue - a.numValue); // 按值从大到小排序

      // 计算 Y 轴像素高度（估算）
      const chartHeight = containerHeight || 300;
      const yMin = 0;
      const yMax =
        typeof yAxisDomain[1] === 'number'
          ? yAxisDomain[1]
          : Math.max(...validItems.map((i) => i.numValue), 1);
      const yRange = yMax - yMin || 1;

      // 为每个标签计算 dy 偏移量，避免重叠
      const MIN_LABEL_DISTANCE = 20; // 最小标签间距（像素）
      const OFFSET_STEP = 14; // 每次偏移的像素值
      const BOTTOM_SAFE_ZONE = 30; // 底部安全区域（像素），避免与 X 轴重叠
      const labelOffsets: Record<string, number> = {};
      let accumulatedOffset = 0;

      for (let i = 0; i < validItems.length; i++) {
        const current = validItems[i];
        // 计算当前阈值距离底部的像素距离
        const distanceFromBottom = (current.numValue / yRange) * chartHeight;

        if (i === 0) {
          labelOffsets[current.level] = 0;
        } else {
          const prev = validItems[i - 1];
          // 计算两个阈值在 Y 轴上的像素距离
          const pixelDistance =
            ((prev.numValue - current.numValue) / yRange) * chartHeight;

          if (pixelDistance < MIN_LABEL_DISTANCE) {
            // 距离太近，累加偏移
            accumulatedOffset += OFFSET_STEP;
            labelOffsets[current.level] = accumulatedOffset;
          } else {
            // 距离足够，重置偏移
            accumulatedOffset = 0;
            labelOffsets[current.level] = 0;
          }
        }

        // 如果标签加上偏移后会超出底部安全区域，改为向上偏移
        const totalOffset = labelOffsets[current.level];
        if (distanceFromBottom < BOTTOM_SAFE_ZONE + totalOffset) {
          // 改为向上偏移（负值）
          labelOffsets[current.level] = -Math.abs(totalOffset) - 4;
        }
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
      yAxisDomain
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
          const numValue = Number(payload.value);
          label = Number.isInteger(numValue)
            ? String(numValue)
            : numValue.toFixed(2);
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
        ref={containerRef}
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
                  right: rightMargin,
                  left: 0,
                  bottom: 0
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
                  domain={yAxisDomain}
                />

                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <Tooltip
                  offset={-1}
                  content={
                    <CustomTooltip
                      unit={unit}
                      visible={!isDragging}
                      metric={metric as MetricItem}
                      maxHeight={
                        containerHeight ? containerHeight * 0.75 : undefined
                      }
                      maxWidth={
                        containerWidth ? containerWidth * 0.8 : undefined
                      }
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
                {/* 为每个阈值级别渲染阴影区域 */}
                {validThresholds.map((item, index) => {
                  const levelColor =
                    (LEVEL_MAP[item.level] as string) || '#F43B2C';
                  // 将颜色转换为 rgba 格式，透明度 0.1
                  const fillColor = levelColor.startsWith('#')
                    ? `rgba(${parseInt(levelColor.slice(1, 3), 16)}, ${parseInt(levelColor.slice(3, 5), 16)}, ${parseInt(levelColor.slice(5, 7), 16)}, 0.1)`
                    : levelColor;

                  const yMax =
                    yAxisDomain[1] === 'auto' ? undefined : yAxisDomain[1];

                  // = 等于：不显示阴影区域（只显示阈值线）
                  if (item.method === '=') {
                    return null;
                  }

                  // != 不等于：显示全部区域（0 到最大值）
                  if (item.method === '!=') {
                    return (
                      <ReferenceArea
                        key={`area-${item.level}-${index}`}
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

                {/* 阈值线的可视部分（实线） */}
                {threshold.map((item, index) => {
                  const formattedValue = formatThresholdValue(
                    item.value as number
                  );
                  const originalValue = String(item.value);
                  const levelColor =
                    (LEVEL_MAP[item.level] as string) || '#F43B2C';
                  const fullText = `${levelNameMap[item.level] || item.level} ${originalValue}`;
                  const dy = thresholdLabelInfo.labelOffsets[item.level] || 0;

                  return (
                    <ReferenceLine
                      key={`visual-${index}`}
                      y={`${item.value}`}
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
