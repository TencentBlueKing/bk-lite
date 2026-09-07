'use client';

import { useEffect, useState } from 'react';
import { Spin } from 'antd';
import dayjs from 'dayjs';

import { useAlarmApi } from '@/app/alarm/api/alarms';
import { useCommonApi } from '@/app/alarm/api/common';
import StackedBarChart from '@/app/alarm/components/stackedBarChart';
import type { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import type { LevelItem } from '@/app/alarm/types/index';
import { processDataForStackedBarChart } from '@/app/alarm/utils/alarmChart';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

import { extractAlarmListItems } from './listPayload';

export interface AlarmTrendChartProps {
  timeRange?: number[];
  refreshKey?: number;
}

export default function AlarmTrendChart({
  timeRange = [],
  refreshKey = 0,
}: AlarmTrendChartProps) {
  const { getAlarmList } = useAlarmApi();
  const { getLevelList } = useCommonApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<Array<Record<string, unknown>>>([]);
  const [colors, setColors] = useState<Record<string, string>>({});

  const rangeKey = `${timeRange[0] ?? ''}:${timeRange[1] ?? ''}`;

  useEffect(() => {
    let cancelled = false;
    const [start, end] = timeRange;
    setLoading(true);

    Promise.all([
      getLevelList(),
      getAlarmList({
        page: 1,
        page_size: 1000,
        created_at_after: start ? dayjs(start).toISOString() : '',
        created_at_before: end ? dayjs(end).toISOString() : '',
      }),
    ])
      .then(([levels, payload]) => {
        if (cancelled) return;
        const alertLevels = (levels || []).filter(
          (item: LevelItem) => item.level_type === 'alert'
        );
        setColors(
          Object.fromEntries(
            alertLevels.map((item) => [item.level_display_name, item.color])
          )
        );
        const items = extractAlarmListItems<AlarmTableDataItem>(payload).filter(
          (item) => !!item.level
        );
        setData(
          processDataForStackedBarChart(
            items,
            alertLevels,
            convertToLocalizedTime
          ) as Array<Record<string, unknown>>
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // 请求包装每次 render 都会换身份，刷新只跟时间范围和显式 refreshKey 走。
  }, [convertToLocalizedTime, rangeKey, refreshKey, timeRange]);

  return (
    <Spin spinning={loading}>
      <div className="h-[240px] w-full">
        <StackedBarChart data={data} colors={colors} />
      </div>
    </Spin>
  );
}
