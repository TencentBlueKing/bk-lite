'use client';

import React, { useState, useMemo, useCallback } from 'react';
import { Button, Radio, DatePicker, Tooltip } from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import isSameOrAfter from 'dayjs/plugin/isSameOrAfter';
import isSameOrBefore from 'dayjs/plugin/isSameOrBefore';
import isBetween from 'dayjs/plugin/isBetween';
import minMax from 'dayjs/plugin/minMax';
import { useTranslation } from '@/utils/i18n';
import { HeatMapDataItem } from '@/types';

dayjs.extend(isSameOrAfter);
dayjs.extend(isSameOrBefore);
dayjs.extend(isBetween);
dayjs.extend(minMax);

interface EventHeatMapProps {
  data: HeatMapDataItem[];
  className?: string;
}

const EventHeatMap: React.FC<EventHeatMapProps> = ({
  data = [],
  className = '',
}) => {
  const { t } = useTranslation();
  const [viewMode, setViewMode] = useState<'month' | 'day'>('month');
  const [currentDate, setCurrentDate] = useState<Dayjs>(dayjs());

  // 获取数据中最新的日期作为默认日期
  const latestDate = useMemo(() => {
    if (!data.length) return dayjs();
    const dates = data.map((item) => dayjs(item.event_time));
    return dayjs.max(dates) || dayjs();
  }, [data]);

  // 初始化时设置为最新日期
  React.useEffect(() => {
    setCurrentDate(latestDate);
  }, [latestDate]);

  // 按小时聚合数据（用于按天模式）
  const processedHourData = useMemo(() => {
    const hourMap = new Map<string, number>();

    data.forEach((item) => {
      const eventTime = dayjs(item.event_time);
      const hour = eventTime.format('YYYY/MM/DD HH:00:00');
      const existing = hourMap.get(hour) || 0;

      hourMap.set(hour, existing + 1);
    });

    return Array.from(hourMap.entries()).map(([hour, count]) => ({
      date: hour,
      count,
    }));
  }, [data]);

  // 按天聚合数据（用于按月模式）
  const processedData = useMemo(() => {
    const dateMap = new Map<string, number>();

    data.forEach((item) => {
      const date = dayjs(item.event_time).format('YYYY/MM/DD');
      const existing = dateMap.get(date) || 0;

      dateMap.set(date, existing + 1);
    });

    return Array.from(dateMap.entries()).map(([date, count]) => ({
      date,
      count,
    }));
  }, [data]);

  // 获取显示范围的数据
  const displayData = useMemo(() => {
    if (viewMode === 'month') {
      // 按月显示 - 生成当前月的所有天数
      const monthStart = currentDate.startOf('month');
      const daysInMonth = currentDate.daysInMonth();

      const monthData = [];
      for (let day = 1; day <= daysInMonth; day++) {
        const dayTime = monthStart.date(day);
        const dateKey = dayTime.format('YYYY/MM/DD');

        // 查找该日期的实际数据
        const existingData = processedData.find(
          (item) => item.date === dateKey
        );

        monthData.push({
          date: dateKey,
          count: existingData?.count || 0,
        });
      }

      return monthData;
    } else {
      // 按天显示（显示选定日期的24小时）
      const dayStart = currentDate.startOf('day');

      // 生成24小时的完整数据，即使某些小时没有数据
      const hourlyData = [];
      for (let hour = 0; hour < 24; hour++) {
        const hourTime = dayStart.hour(hour);
        const hourKey = hourTime.format('YYYY/MM/DD HH:00:00');

        // 查找该小时的实际数据
        const existingData = processedHourData.find(
          (item) => item.date === hourKey
        );

        hourlyData.push({
          date: hourKey,
          count: existingData?.count || 0,
        });
      }

      return hourlyData;
    }
  }, [currentDate, viewMode, processedData, processedHourData]);

  // 获取格子的颜色
  const getCellColor = useCallback((count: number, mode: 'month' | 'day') => {
    if (count === 0) return 'var(--color-fill-4)';
    if (mode === 'month') {
      if (count <= 5) return '#ffd6cc';
      if (count <= 15) return '#ff9d8a';
      return 'var(--color-fail)';
    } else {
      if (count <= 2) return '#ffd6cc';
      if (count <= 5) return '#ff9d8a';
      return 'var(--color-fail)';
    }
  }, []);

  // 图例配置
  const legendConfig = useMemo(() => {
    if (viewMode === 'month') {
      return [
        { color: 'var(--color-fill-4)', label: '0' },
        { color: '#ffd6cc', label: '1-5' },
        { color: '#ff9d8a', label: '6-15' },
        { color: 'var(--color-fail)', label: '16+' },
      ];
    } else {
      return [
        { color: 'var(--color-fill-4)', label: '0' },
        { color: '#ffd6cc', label: '1-2' },
        { color: '#ff9d8a', label: '3-5' },
        { color: 'var(--color-fail)', label: '6+' },
      ];
    }
  }, [viewMode]);

  // 导航函数
  const navigate = useCallback(
    (direction: 'prev' | 'next') => {
      const today = dayjs();
      const newDate =
        viewMode === 'month'
          ? currentDate.add(direction === 'prev' ? -1 : 1, 'month')
          : currentDate.add(direction === 'prev' ? -1 : 1, 'day');

      // 限制不能导航到今天之后的日期
      if (direction === 'next') {
        if (viewMode === 'month') {
          // 按月模式：不能超过当前月
          if (newDate.isAfter(today, 'month')) {
            return;
          }
        } else {
          // 按天模式：不能超过今天
          if (newDate.isAfter(today, 'day')) {
            return;
          }
        }
      }

      setCurrentDate(newDate);
    },
    [currentDate, viewMode]
  );

  // 检查下一个导航按钮是否应该禁用
  const isNextDisabled = useMemo(() => {
    const today = dayjs();
    if (viewMode === 'month') {
      return currentDate.isSameOrAfter(today, 'month');
    } else {
      return currentDate.isSameOrAfter(today, 'day');
    }
  }, [currentDate, viewMode]);

  // 日期选择器禁用日期函数
  const disabledDate = useCallback(
    (date: Dayjs) => {
      const today = dayjs();
      if (viewMode === 'month') {
        // 按月模式：禁用今天所在月份之后的月份
        return date.isAfter(today, 'month');
      } else {
        // 按天模式：禁用今天之后的日期
        return date.isAfter(today, 'day');
      }
    },
    [viewMode]
  );

  // 日期选择器变化
  const handleDateChange = useCallback((date: Dayjs | null) => {
    if (date) {
      setCurrentDate(date);
    }
  }, []);

  return (
    <div
      className={`bg-[var(--color-fill-1)] p-[10px] rounded-sm ${className}`}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-4">
          <Radio.Group
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value)}
            size="small"
          >
            <Radio.Button value="month">
              {t('common.heatMap.monthDisplay')}
            </Radio.Button>
            <Radio.Button value="day">
              {t('common.heatMap.dayDisplay')}
            </Radio.Button>
          </Radio.Group>
        </div>

        <div className="flex items-center space-x-2">
          <Button
            size="small"
            icon={<LeftOutlined />}
            onClick={() => navigate('prev')}
          />
          <DatePicker
            value={currentDate}
            onChange={handleDateChange}
            picker={viewMode === 'month' ? 'month' : 'date'}
            size="small"
            format={viewMode === 'month' ? 'YYYY-MM' : 'YYYY-MM-DD'}
            placeholder={
              viewMode === 'month'
                ? t('common.heatMap.selectMonth')
                : t('common.heatMap.selectDate')
            }
            allowClear={false}
            className="min-w-[120px]"
            disabledDate={disabledDate}
          />
          <Button
            size="small"
            icon={<RightOutlined />}
            onClick={() => navigate('next')}
            disabled={isNextDisabled}
          />
        </div>
      </div>

      {/* 自定义热力图 */}
      <div className="flex justify-center mb-2">
        <div
          className={`grid gap-1 w-full ${
            viewMode === 'month' ? 'grid-cols-12' : 'grid-cols-8'
          }`}
          style={{ maxWidth: '100%' }}
        >
          {displayData.map((cellData, index) => {
            const color = getCellColor(cellData.count, viewMode);

            // 生成 tooltip 内容
            let tooltipTitle: React.ReactNode;
            if (viewMode === 'month') {
              const dateStr = dayjs(cellData.date).format('YYYY-MM-DD');
              tooltipTitle = (
                <div>
                  <div>{dateStr}</div>
                  <div>
                    {t('common.heatMap.quantity')}：{cellData.count}
                  </div>
                </div>
              );
            } else {
              const startTime = dayjs(cellData.date);
              const hour = startTime.hour();
              const dateStr = startTime.format('YYYY-MM-DD');
              tooltipTitle = (
                <div>
                  <div>
                    {dateStr} {hour.toString().padStart(2, '0')}:00:00-
                    {hour.toString().padStart(2, '0')}:59:59
                  </div>
                  <div>
                    {t('common.heatMap.quantity')}：{cellData.count}
                  </div>
                </div>
              );
            }

            return (
              <Tooltip key={index} title={tooltipTitle}>
                <div className="flex flex-col items-center">
                  <div
                    className="h-6 rounded transition-all duration-200 hover:scale-105 hover:shadow-md flex items-center justify-center relative w-full"
                    style={{
                      backgroundColor: color,
                    }}
                  >
                    <span
                      className="text-[12px] font-medium select-none"
                      style={{ color: 'var(--color-bg)' }}
                    >
                      {cellData.count}
                    </span>
                  </div>
                  <div
                    className="text-[12px] font-medium select-none text-center mt-[2px]"
                    style={{ color: 'var(--color-text-3)' }}
                  >
                    {
                      viewMode === 'month'
                        ? `Day${dayjs(cellData.date).date()}` // 显示day+日期数字
                        : `${dayjs(cellData.date)
                          .hour()
                          .toString()
                          .padStart(2, '0')}:00-${dayjs(cellData.date)
                          .hour()
                          .toString()
                          .padStart(2, '0')}:59` // 显示时间段
                    }
                  </div>
                </div>
              </Tooltip>
            );
          })}
        </div>
      </div>

      {/* 图例说明 */}
      <div className="flex items-center justify-center space-x-4 text-xs">
        <div className="flex space-x-2 items-center">
          {legendConfig.map((legend, index) => (
            <div key={index} className="flex items-center space-x-1">
              <div
                className="w-3 h-3 rounded"
                style={{ backgroundColor: legend.color }}
              ></div>
              <span className="text-[var(--color-text-3)]">{legend.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default EventHeatMap;
