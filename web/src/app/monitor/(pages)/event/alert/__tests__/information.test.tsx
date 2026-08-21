import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TableDataItem } from '@/app/monitor/types';
import zh from '@/app/monitor/locales/zh.json';
import Information from '../information';

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({ convertToLocalizedTime: (value: string) => value })
}));

vi.mock('@/app/monitor/components/charts/lineChart', () => ({
  default: () => <div data-testid="line-chart" />
}));

vi.mock('@/app/monitor/hooks/useUnitTransform', () => ({
  useUnitTransform: () => ({ findUnitNameById: () => '%' })
}));

vi.mock('@/app/monitor/context/common', () => ({
  useCommon: () => ({ authOrganizations: [] })
}));

vi.mock('@/app/monitor/api', () => ({
  default: () => ({ patchMonitorAlert: vi.fn() })
}));

vi.mock('@/app/monitor/hooks', () => ({
  useLevelList: () => [{ value: 'critical', label: '严重' }]
}));

vi.mock('@/components/permission', () => ({
  default: ({ children }: React.PropsWithChildren) => <>{children}</>
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const value = key
        .split('.')
        .reduce<unknown>((current, segment) => {
          if (!current || typeof current !== 'object') return undefined;
          return (current as Record<string, unknown>)[segment];
        }, zh);
      return typeof value === 'string' ? value : key;
    }
  })
}));

beforeEach(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn()
  });
});

afterEach(cleanup);

describe('告警详情信息', () => {
  it('使用语言包标题展示告警维度', () => {
    const formData = {
      id: 'alert-1',
      status: 'closed',
      level: 'critical',
      updated_at: '2026-08-19 10:00:00',
      start_event_time: '2026-08-19 09:00:00',
      content: 'CPU 使用率过高',
      monitor_instance_name: 'node-01',
      alert_type: 'threshold',
      metric: {
        display_name: 'CPU 使用率',
        dimensions: [{ name: 'instance', description: '实例' }]
      },
      dimensions: { instance: 'node-01' },
      policy: {
        monitor_object: 1,
        organizations: [],
        name: 'CPU 策略',
        notice: false,
        notice_users: [],
        threshold: [],
        query_condition: { type: 'metric' }
      },
      permission: ['Operate', 'Detail']
    } as unknown as TableDataItem;

    render(
      <Information
        formData={formData}
        chartData={[]}
        objects={[
          { id: 1, name: 'host', display_name: '主机', icon: '' }
        ]}
        userList={[]}
        onClose={vi.fn()}
        trapData={{}}
      />
    );

    expect(screen.getByText('维度')).toBeTruthy();
    expect(screen.queryByText('monitor.events.dimension')).toBeNull();
    expect(screen.getByText('实例:')).toBeTruthy();
    expect(screen.getAllByText('node-01')).toHaveLength(2);
  });
});
