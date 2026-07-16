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
import type { HeatMapDataItem } from '@/types';

dayjs.extend(isSameOrAfter);
dayjs.extend(isSameOrBefore);
dayjs.extend(isBetween);
dayjs.extend(minMax);

type HeatMapViewMode = 'month' | 'day';

export function getHeatMapCellColor(
  count: number,
  mode: HeatMapViewMode
): string {
  if (count === 0) return 'var(--color-fill-4)';
  if (mode === 'month') {
    if (count <= 5) return '#ffd6cc';
    if (count <= 15) return '#ff9d8a';
    return 'var(--color-fail)';
  }
  if (count <= 2) return '#ffd6cc';
  if (count <= 5) return '#ff9d8a';
  return 'var(--color-fail)';
}

interface HeatMapCellData {
  date: string;
  count: number;
  startTime: string;
  endTime: string;
}

export interface HeatMapCellClickPayload {
  mode: HeatMapViewMode;
  count: number;
  startTime: string;
  endTime: string;
}

interface EventHeatMapProps {
  data: HeatMapDataItem[];
  className?: string;
  onCellClick?: (payload: HeatMapCellClickPayload) => void;
}

const EventHeatMap: React.FC<EventHeatMapProps> = ({
  data = [],
  className = '',
  onCellClick,
}) => {
  const { t } = useTranslation();
  const [viewMode, setViewMode] = useState<HeatMapViewMode>('month');
  const [currentDate, setCurrentDate] = useState<Dayjs>(dayjs());

  const latestDate = useMemo(() => {
    if (!data.length) return dayjs();
    const dates = data.map((item) => dayjs(item.event_time));
    return dayjs.max(dates) || dayjs();
  }, [data]);

  React.useEffect(() => {
    setCurrentDate(latestDate);
  }, [latestDate]);

  const processedHourData = useMemo(() => {
    const hourMap = new Map<string, number>();

    data.forEach((item) => {
      const eventTime = dayjs(item.event_time);
      const hour = eventTime.format('YYYY/MM/DD HH:00:00');
      const existing = hourMap.get(hour) || 0;

      hourMap.set(hour, existing + 1);
    });

    return Array.from(hourMap.entries()).map(([hour, count]) => {
      const startTime = dayjs(hour, 'YYYY/MM/DD HH:mm:ss');
      return {
        date: hour,
        count,
        startTime: startTime.toISOString(),
        endTime: startTime.add(1, 'hour').toISOString(),
      };
    });
  }, [data]);

  const processedData = useMemo(() => {
    const dateMap = new Map<string, number>();

    data.forEach((item) => {
      const date = dayjs(item.event_time).format('YYYY/MM/DD');
      const existing = dateMap.get(date) || 0;

      dateMap.set(date, existing + 1);
    });

    return Array.from(dateMap.entries()).map(([date, count]) => {
      const startTime = dayjs(date, 'YYYY/MM/DD');
      return {
        date,
        count,
        startTime: startTime.toISOString(),
        endTime: startTime.add(1, 'day').toISOString(),
      };
    });
  }, [data]);

  const displayData = useMemo(() => {
    if (viewMode === 'month') {
      const monthStart = currentDate.startOf('month');
      const daysInMonth = currentDate.daysInMonth();
      const monthData: HeatMapCellData[] = [];

      for (let day = 1; day <= daysInMonth; day++) {
        const dayTime = monthStart.date(day);
        const dateKey = dayTime.format('YYYY/MM/DD');
        const existingData = processedData.find((item) => item.date === dateKey);

        monthData.push({
          date: dateKey,
          count: existingData?.count || 0,
          startTime: dayTime.startOf('day').toISOString(),
          endTime: dayTime.startOf('day').add(1, 'day').toISOString(),
        });
      }

      return monthData;
    }

    const dayStart = currentDate.startOf('day');
    const hourlyData: HeatMapCellData[] = [];

    for (let hour = 0; hour < 24; hour++) {
      const hourTime = dayStart.hour(hour);
      const hourKey = hourTime.format('YYYY/MM/DD HH:00:00');
      const existingData = processedHourData.find((item) => item.date === hourKey);

      hourlyData.push({
        date: hourKey,
        count: existingData?.count || 0,
        startTime: hourTime.startOf('hour').toISOString(),
        endTime: hourTime.startOf('hour').add(1, 'hour').toISOString(),
      });
    }

    return hourlyData;
  }, [currentDate, viewMode, processedData, processedHourData]);

  const legendConfig = useMemo(() => {
    if (viewMode === 'month') {
      return [
        { color: 'var(--color-fill-4)', label: '0' },
        { color: '#ffd6cc', label: '1-5' },
        { color: '#ff9d8a', label: '6-15' },
        { color: 'var(--color-fail)', label: '16+' },
      ];
    }

    return [
      { color: 'var(--color-fill-4)', label: '0' },
      { color: '#ffd6cc', label: '1-2' },
      { color: '#ff9d8a', label: '3-5' },
      { color: 'var(--color-fail)', label: '6+' },
    ];
  }, [viewMode]);

  const navigate = useCallback((direction: 'prev' | 'next') => {
    const today = dayjs();
    const newDate =
      viewMode === 'month'
        ? currentDate.add(direction === 'prev' ? -1 : 1, 'month')
        : currentDate.add(direction === 'prev' ? -1 : 1, 'day');

    if (direction === 'next') {
      if (viewMode === 'month') {
        if (newDate.isAfter(today, 'month')) return;
      } else if (newDate.isAfter(today, 'day')) {
        return;
      }
    }

    setCurrentDate(newDate);
  }, [currentDate, viewMode]);

  const isNextDisabled = useMemo(() => {
    const today = dayjs();
    return viewMode === 'month'
      ? currentDate.isSameOrAfter(today, 'month')
      : currentDate.isSameOrAfter(today, 'day');
  }, [currentDate, viewMode]);

  const disabledDate = useCallback((current: Dayjs) => {
    const today = dayjs();
    if (viewMode === 'month') {
      return current && current.isAfter(today.endOf('month'));
    }
    return current && current.isAfter(today.endOf('day'));
  }, [viewMode]);

  const handleCellClick = useCallback((cellData: HeatMapCellData) => {
    onCellClick?.({
      mode: viewMode,
      count: cellData.count,
      startTime: cellData.startTime,
      endTime: cellData.endTime,
    });
  }, [onCellClick, viewMode]);

  const renderMonthGrid = useMemo(() => {
    const monthStart = currentDate.startOf('month');
    const firstDayOfWeek = monthStart.day();
    const cells: Array<HeatMapCellData | null> = [];

    for (let i = 0; i < firstDayOfWeek; i++) {
      cells.push(null);
    }

    displayData.forEach((item) => cells.push(item));
    return cells;
  }, [currentDate, displayData]);

  return (
    <div className={className}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Radio.Group
          value={viewMode}
          onChange={(event) => setViewMode(event.target.value)}
          optionType="button"
          buttonStyle="solid"
        >
          <Radio.Button value="month">{t('common.month')}</Radio.Button>
          <Radio.Button value="day">{t('common.day')}</Radio.Button>
        </Radio.Group>

        <div className="flex items-center gap-2">
          <Button
            icon={<LeftOutlined />}
            onClick={() => navigate('prev')}
            aria-label={t('common.previous')}
          />
          <DatePicker
            picker={viewMode === 'month' ? 'month' : undefined}
            value={currentDate}
            onChange={(value) => value && setCurrentDate(value)}
            disabledDate={disabledDate}
            allowClear={false}
          />
          <Button
            icon={<RightOutlined />}
            onClick={() => navigate('next')}
            disabled={isNextDisabled}
            aria-label={t('common.next')}
          />
        </div>
      </div>

      {viewMode === 'month' ? (
        <div className="grid grid-cols-7 gap-2">
          {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((dayLabel) => (
            <div key={dayLabel} className="text-center text-xs text-[var(--color-text-3)]">
              {dayLabel}
            </div>
          ))}
          {renderMonthGrid.map((cellData, index) => (
            <div key={cellData?.date || `empty-${index}`} className="aspect-square">
              {cellData ? (
                <Tooltip title={`${cellData.date}: ${cellData.count}`}>
                  <button
                    type="button"
                    onClick={() => handleCellClick(cellData)}
                    className="flex h-full w-full items-center justify-center rounded text-xs transition-opacity hover:opacity-85"
                    style={{
                      backgroundColor: getHeatMapCellColor(cellData.count, viewMode),
                    }}
                  >
                    {dayjs(cellData.date, 'YYYY/MM/DD').date()}
                  </button>
                </Tooltip>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-6 gap-2">
          {displayData.map((cellData) => (
            <Tooltip
              key={cellData.date}
              title={`${dayjs(cellData.date, 'YYYY/MM/DD HH:mm:ss').format('HH:mm')}: ${cellData.count}`}
            >
              <button
                type="button"
                onClick={() => handleCellClick(cellData)}
                className="flex h-10 items-center justify-center rounded text-xs transition-opacity hover:opacity-85"
                style={{
                  backgroundColor: getHeatMapCellColor(cellData.count, viewMode),
                }}
              >
                {dayjs(cellData.date, 'YYYY/MM/DD HH:mm:ss').format('HH:mm')}
              </button>
            </Tooltip>
          ))}
        </div>
      )}

      <div className="mt-4 flex items-center gap-3 text-xs text-[var(--color-text-3)]">
        <span>{t('common.level')}</span>
        {legendConfig.map((legend) => (
          <div key={legend.label} className="flex items-center gap-1">
            <span
              className="inline-block h-3 w-3 rounded-sm"
              style={{ backgroundColor: legend.color }}
            />
            <span>{legend.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default EventHeatMap;
