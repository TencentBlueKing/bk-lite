import { describe, expect, it } from 'vitest';

import { slots, TrendChart } from '@/app/alarm/capability';

describe('alarm capability', () => {
  it('registers the monitor extra-tab trend chart', () => {
    expect(TrendChart).toBeTypeOf('function');
    expect(slots['monitor.event.extraTabs']).toMatchObject({
      key: 'alarmTrend',
      labelKey: 'alarms.capability.alarmTrend',
      labelDefault: '告警趋势',
    });
    expect(slots['monitor.event.extraTabs'].component).toBe(TrendChart);
  });
});
