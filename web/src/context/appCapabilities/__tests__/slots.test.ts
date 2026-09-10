import { describe, expect, it } from 'vitest';

import {
  collectSlotContributions,
  isHostTab,
  resolveSlot,
} from '../slots';

const TrendChart = () => null;

describe('collectSlotContributions', () => {
  it('collects matching slots and ignores missing or incomplete entries', () => {
    const contributions = collectSlotContributions(
      [
        null,
        {
          appName: 'alarm',
          slots: {
            'monitor.event.extraTabs': {
              key: 'alarmTrend',
              labelKey: 'alarms.capability.alarmTrend',
              labelDefault: '告警趋势',
              component: TrendChart,
            },
          },
        },
        {
          appName: 'log',
          slots: {
            'monitor.event.extraTabs': {
              key: '',
              labelKey: 'x',
              labelDefault: 'x',
              component: TrendChart,
            },
          },
        },
      ],
      'monitor.event.extraTabs'
    );

    expect(contributions).toEqual([
      {
        appName: 'alarm',
        key: 'alarmTrend',
        labelKey: 'alarms.capability.alarmTrend',
        labelDefault: '告警趋势',
        component: TrendChart,
      },
    ]);
  });
});

describe('resolveSlot', () => {
  it('finds the contribution for the active extra tab', () => {
    const contributions = collectSlotContributions(
      [
        {
          appName: 'alarm',
          slots: {
            'monitor.event.extraTabs': {
              key: 'alarmTrend',
              labelKey: 'alarms.capability.alarmTrend',
              labelDefault: '告警趋势',
              component: TrendChart,
            },
          },
        },
      ],
      'monitor.event.extraTabs'
    );

    expect(resolveSlot(contributions, 'alarmTrend')?.appName).toBe('alarm');
    expect(resolveSlot(contributions, 'missing')).toBeNull();
  });
});

describe('isHostTab', () => {
  it('treats unknown extra keys as host tabs', () => {
    expect(isHostTab('activeAlarms', ['alarmTrend'])).toBe(true);
    expect(isHostTab('alarmTrend', ['alarmTrend'])).toBe(false);
  });
});
