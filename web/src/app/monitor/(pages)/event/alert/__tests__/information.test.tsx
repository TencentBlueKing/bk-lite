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
  default: () => ({
    patchMonitorAlert: vi.fn(),
    claimMonitorAlert: vi.fn(),
    assignMonitorAlert: vi.fn(),
    reassignMonitorAlert: vi.fn(),
    getAllUsers: vi.fn().mockResolvedValue([])
  })
}));

vi.mock('@/app/monitor/hooks', () => ({
  useLevelList: () => [{ value: 'critical', label: '严重' }]
}));

vi.mock('@/components/permission', () => ({
  default: ({ children }: React.PropsWithChildren) => <>{children}</>
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => ({ userId: '7', username: 'testuser' })
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

  it('空处理人的活跃告警展示认领、分派和关闭', () => {
    const formData = {
      id: 'alert-2',
      status: 'new',
      handlers: [],
      permission: ['Operate', 'Detail'],
      policy: { notice: false, query_condition: { type: 'metric' } },
    } as unknown as TableDataItem;

    render(
      <Information
        formData={formData}
        chartData={[]}
        objects={[]}
        userList={[]}
        onClose={vi.fn()}
        trapData={{}}
      />
    );

    const claim = screen.getByRole('button', { name: /^认\s*领$/ });
    const assign = screen.getByRole('button', { name: /^分\s*派$/ });
    const close = screen.getByRole('button', { name: /^关\s*闭$/ });
    expect(claim.className).toContain('ant-btn-link');
    expect(assign.className).toContain('ant-btn-link');
    expect(close.className).toContain('ant-btn-link');
    expect(close.className).not.toContain('ant-btn-dangerous');
    expect(screen.queryByRole('button', { name: /^转\s*派$/ })).toBeNull();
  });

  it('已有处理人的活跃告警不展示认领和分派', () => {
    const formData = {
      id: 'alert-3',
      status: 'new',
      handlers: [7],
      handlers_display: ['Bob(bob)'],
      permission: ['Operate', 'Detail'],
      policy: { notice: false, query_condition: { type: 'metric' } },
    } as unknown as TableDataItem;

    render(
      <Information
        formData={formData}
        chartData={[]}
        objects={[]}
        userList={[]}
        onClose={vi.fn()}
        trapData={{}}
      />
    );

    expect(screen.getByText('Bob(bob)')).not.toBeNull();
    expect(screen.queryByRole('button', { name: /^认\s*领$/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^分\s*派$/ })).toBeNull();
    expect(screen.getByRole('button', { name: /^转\s*派$/ })).not.toBeNull();
    expect(screen.getByRole('button', { name: /^关\s*闭$/ })).not.toBeNull();
  });

  it('不是当前处理人时不展示关闭', () => {
    const formData = {
      id: 'alert-5',
      status: 'new',
      handlers: [8],
      handlers_display: ['Alice(alice)'],
      permission: ['Operate', 'Detail'],
      policy: { notice: false, query_condition: { type: 'metric' } },
    } as unknown as TableDataItem;

    render(
      <Information
        formData={formData}
        chartData={[]}
        objects={[]}
        userList={[]}
        onClose={vi.fn()}
        trapData={{}}
      />
    );

    expect(screen.queryByRole('button', { name: /^关\s*闭$/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /^转\s*派$/ })).toBeNull();
  });

  it('does not throw when objects is omitted or empty and falls back to --', () => {
    const formData = {
      id: 'alert-4',
      status: 'closed',
      level: 'critical',
      content: '磁盘告警',
      monitor_instance_name: 'node-02',
      policy: {
        monitor_object: 1,
        organizations: [],
        name: 'Disk',
        notice: false,
        notice_users: [],
        query_condition: { type: 'metric' },
      },
      permission: ['Detail'],
    } as unknown as TableDataItem;

    expect(() =>
      render(
        <Information
          formData={formData}
          chartData={[]}
          userList={[]}
          onClose={vi.fn()}
          trapData={{}}
        />,
      ),
    ).not.toThrow();
    expect(screen.getAllByText('--').length).toBeGreaterThan(0);

    cleanup();

    expect(() =>
      render(
        <Information
          formData={formData}
          chartData={[]}
          objects={[]}
          userList={[]}
          onClose={vi.fn()}
          trapData={{}}
        />,
      ),
    ).not.toThrow();
  });

  it('still shows the object display name when objects is provided', () => {
    const formData = {
      id: 'alert-5',
      status: 'closed',
      level: 'critical',
      content: '磁盘告警',
      monitor_instance_name: 'node-02',
      policy: {
        monitor_object: 1,
        organizations: [],
        name: 'Disk',
        notice: false,
        notice_users: [],
        query_condition: { type: 'metric' },
      },
      permission: ['Detail'],
    } as unknown as TableDataItem;

    render(
      <Information
        formData={formData}
        chartData={[]}
        objects={[{ id: 1, name: 'Host', display_name: '主机', icon: '' }]}
        userList={[]}
        onClose={vi.fn()}
        trapData={{}}
      />,
    );
    expect(screen.getAllByText('主机').length).toBeGreaterThan(0);
    expect(screen.getByText('资产类型')).toBeTruthy();
  });
});
