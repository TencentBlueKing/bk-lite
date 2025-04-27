import React, { useState, useEffect } from 'react';
import { Empty, Tooltip as Tip } from 'antd';
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
} from 'recharts';
import CustomTooltip from './customTooltips';
import {
  generateUniqueRandomColor,
  useFormatTime,
  isStringArray,
} from '@/app/monitor/utils/common';
import chartLineStyle from './index.module.scss';
import dayjs, { Dayjs } from 'dayjs';
import DimensionFilter from './dimensionFilter';
import DimensionTable from './dimensionTable';
import { ChartData, ListItem, TableDataItem } from '@/app/monitor/types';
import { MetricItem, ThresholdField } from '@/app/monitor/types/monitor';
import { LEVEL_MAP } from '@/app/monitor/constants/monitor';
import useApiClient from '@/utils/request';
import { isNumber } from 'lodash';

interface LineChartProps {
  data: ChartData[];
  unit?: string;
  metric?: MetricItem;
  threshold?: ThresholdField[];
  formID?: number;
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

const LineChart: React.FC<LineChartProps> = ({
  data,
  unit = '',
  showDimensionFilter = false,
  metric = {},
  threshold = [],
  formID = null,
  allowSelect = true,
  showDimensionTable = false,
  onXRangeChange,
}) => {
  const { formatTime } = useFormatTime();
  const { get } = useApiClient();
  const [startX, setStartX] = useState<number | null>(null);
  const [endX, setEndX] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [colors, setColors] = useState<string[]>([]);
  const [visibleAreas, setVisibleAreas] = useState<string[]>([]);
  const [details, setDetails] = useState<Record<string, any>>({});
  const [hasDimension, setHasDimension] = useState<boolean>(false);
  const [boxItems, setBoxItems] = useState<TableDataItem[]>([]);
  // 获取数据中的最小和最大时间
  const times = data.map((d) => d.time);
  const minTime = +new Date(Math.min(...times));
  const maxTime = +new Date(Math.max(...times));

  useEffect(() => {
    const chartKeys = getChartAreaKeys(data);
    const chartDetails = getDetails(data);
    if (data.length) getEvent();
    setHasDimension(
      !Object.values(chartDetails || {}).every((item) => !item.length)
    );
    setDetails(chartDetails);
    setVisibleAreas(chartKeys); // 默认显示所有area
    const generatedColors = chartKeys.map(() => generateUniqueRandomColor());
    setColors((prev: string[]) => {
      return [
        ...prev,
        ...generatedColors.slice(prev.length, generatedColors.length),
      ];
    });
  }, [data]);

  useEffect(() => {
    getEvent();
  }, [formID]);

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

  const handleMouseDown = (e: any) => {
    if (!allowSelect) return;
    setStartX((pre) => e.activeLabel || pre);
    setIsDragging(true);
    document.body.style.userSelect = 'none'; // 禁用文本选择
  };

  const handleMouseMove = (e: any) => {
    if (!allowSelect) return;
    if (isDragging) {
      setEndX((pre) => e.activeLabel || pre);
    }
  };

  const handleMouseUp = () => {
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
  };

  const handleLegendClick = (key: string) => {
    setVisibleAreas((prevVisibleAreas) =>
      prevVisibleAreas.includes(key)
        ? prevVisibleAreas.filter((area) => area !== key)
        : [...prevVisibleAreas, key]
    );
  };

  const renderYAxisTick = (props: any) => {
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
  };

  const getEvent = async () => {
    if (!formID) return;
    try {
      const _data = await get(`monitor/api/monitor_event/query/${formID}`, {
        params: {
          page: 1,
          page_size: -1,
        },
      });
      const time_intervals: TableDataItem[] = _data.results?.filter(
        (item: any) => {
          const times = timeToSecond(item.created_at);
          if (times >= minTime && times <= maxTime) return true;
          return false;
        }
      );
      const intervals = Math.ceil((maxTime - minTime) / 60);
      const lengths = intervals >= 120 ? 24 : Math.ceil(intervals / 5);
      const step = Math.ceil(_data.results?.length / lengths);
      setBoxItems(handleCutArray(cutArray(time_intervals.reverse(), step)));
    } catch (error) {
      console.log(error);
    }
  };

  const cutArray = (array: TableDataItem[], subLength: number) => {
    let index = 0;
    const newArr = [];
    while (index < array.length) {
      newArr.push(array.slice(index, (index += subLength)));
    }
    return newArr;
  };

  // 对分割的列表进行数据处理
  const handleCutArray = (array: TableDataItem[]) => {
    if (!array) return [];
    const test = array.map((item) => {
      return item
        .sort((prev: TableDataItem, next: TableDataItem) => {
          let flag = null;
          if (prev.value > next.value) {
            flag = 1;
          } else if (prev.value < next.value) {
            flag = -1;
          } else {
            flag =
              timeToSecond(prev.created_at) > timeToSecond(next.created_at)
                ? 1
                : -1;
          }
          return flag;
        })
        .pop();
    });
    return test;
  };

  const timeToSecond = (time: string) => {
    return Math.floor(new Date(time).getTime() / 1000);
  };

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
                right: formID ? 20 : 0,
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
                offset={-40}
                content={
                  <CustomTooltip
                    unit={unit}
                    visible={!isDragging}
                    metric={metric as MetricItem}
                  />
                }
              />
              {getChartAreaKeys(data).map((key, index) => (
                <Area
                  key={index}
                  type="monotone"
                  dataKey={key}
                  stroke={colors[index]}
                  fillOpacity={0}
                  fill={colors[index]}
                  hide={!visibleAreas.includes(key)}
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
          {formID && (
            <div className="flex w-[100%] pl-14 pr-[15px] justify-between">
              {boxItems?.map((item, index) => {
                return (
                  <Tip
                    key={index}
                    title={`${formatTime(
                      Date.parse(item.created_at) / 1000,
                      minTime,
                      maxTime
                    )} ${
                      isNumber(item.value) ? item.value.toFixed(2) : item.value
                    }`}
                  >
                    <span
                      className="flex-1 mr-1 h-2"
                      style={{
                        backgroundColor: LEVEL_MAP[item.level] as string,
                      }}
                    ></span>
                  </Tip>
                );
              })}
            </div>
          )}
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
