'use client';

import AlarmTrendChart from '@/app/alarm/components/alarm-trend-chart';

export const TrendChart = AlarmTrendChart;
export type { AlarmTrendChartProps } from '@/app/alarm/components/alarm-trend-chart';

export const slots = {
  'monitor.event.extraTabs': {
    key: 'alarmTrend',
    labelKey: 'alarms.capability.alarmTrend',
    labelDefault: '告警趋势',
    component: AlarmTrendChart,
  },
};
