import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { SessionProvider } from 'next-auth/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import type { AlarmTableDataItem } from '@/app/alarm/types/alarms';
import type { EventTableItem } from '@/app/alarm/types/integration';
import BaseInfo from '../../(pages)/alarms/components/baseInfo';
import AlarmBaseInfo from '../alarm-base-info';
import AlarmEventTable from '../alarm-event-table';
import EventTable from '../eventTable';
import MonitorObjectList from '../monitor-object-list';

vi.mock('@/app/alarm/context/common', () => ({
  useCommon: () => ({
    levelListEvent: [],
    levelMapEvent: {},
  }),
}));

afterEach(cleanup);

beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
});

const renderWithIntl = (node: React.ReactNode) => render(
  <IntlProvider
    locale="zh"
    messages={{
      'alarms.object': '对象',
      'alarms.objectType': '对象类型',
      'alarms.monitorId': '监控实例 ID',
      'alarms.cmdbId': 'CMDB 实例 ID',
    }}
    onError={() => undefined}
  >
    <SessionProvider session={null}>{node}</SessionProvider>
  </IntlProvider>
);

describe('告警关联监控对象快照', () => {
  it('按对象逐行展示类型和名称，但不暴露 monitor_id 与 cmdb_id', () => {
    const { container } = render(
      <MonitorObjectList
        objects={[
          {
            monitor_id: '0001',
            cmdb_id: 'xxxx1',
            resource_type: '主机',
            resource_name: 'ip1',
          },
          {
            monitor_id: '0002',
            cmdb_id: null,
            resource_type: '交换机',
            resource_name: 'ip2',
          },
        ]}
      />
    );

    expect(screen.getByText('主机：ip1')).toBeTruthy();
    expect(screen.getByText('交换机：ip2')).toBeTruthy();
    expect(container.textContent).not.toContain('0001');
    expect(container.textContent).not.toContain('xxxx1');
    expect(container.textContent).not.toContain('0002');
  });

  it('空类型或名称使用占位符，仍保留对象行', () => {
    render(
      <MonitorObjectList
        objects={[
          {
            monitor_id: '0001',
            cmdb_id: null,
            resource_type: null,
            resource_name: null,
          },
        ]}
      />
    );

    expect(screen.getByText('--：--')).toBeTruthy();
  });

  it('抽屉详情有快照时展示对象集合，并隐藏旧的对象类型行', () => {
    renderWithIntl(
      <AlarmBaseInfo
        detail={{
          resource_type: null,
          resource_name: null,
          monitor_objects: [
            {
              monitor_id: '0001',
              cmdb_id: 'xxxx1',
              resource_type: '主机',
              resource_name: 'ip1',
            },
            {
              monitor_id: '0002',
              cmdb_id: null,
              resource_type: '交换机',
              resource_name: 'ip2',
            },
          ],
        }}
      />
    );

    expect(screen.getByText('主机：ip1')).toBeTruthy();
    expect(screen.getByText('交换机：ip2')).toBeTruthy();
    expect(screen.queryByText('对象类型')).toBeNull();
  });

  it('页面详情有快照时使用同一对象集合展示', () => {
    const detail = {
      content: 'CPU usage exceeded',
      monitor_objects: [
        {
          monitor_id: '0001',
          cmdb_id: null,
          resource_type: '主机',
          resource_name: 'ip1',
        },
      ],
    } as AlarmTableDataItem;

    renderWithIntl(<BaseInfo detail={detail} />);

    expect(screen.getByText('主机：ip1')).toBeTruthy();
    expect(screen.queryByText('对象类型')).toBeNull();
  });

  it('没有快照时保持旧的对象类型与对象展示', () => {
    renderWithIntl(
      <AlarmBaseInfo
        detail={{ resource_type: '主机', resource_name: 'legacy-host' }}
      />
    );

    expect(screen.getByText('对象类型')).toBeTruthy();
    expect(screen.getByText('主机')).toBeTruthy();
    expect(screen.getByText('legacy-host')).toBeTruthy();
  });

  it('关联事件表展示每条事件的 monitor_id 与 cmdb_id', () => {
    renderWithIntl(
      <AlarmEventTable
        dataSource={[
          {
            id: 1,
            level: 'critical',
            monitor_id: '0001',
            cmdb_id: 'xxxx1',
          },
          {
            id: 2,
            level: 'critical',
            monitor_id: '0002',
            cmdb_id: null,
          },
        ]}
        levelOptions={[{ label: '严重', value: 'critical' }]}
        pagination={{ current: 1, pageSize: 20, total: 2 }}
        onChange={() => undefined}
      />
    );

    expect(screen.getAllByText('监控实例 ID').length).toBeGreaterThan(0);
    expect(screen.getAllByText('CMDB 实例 ID').length).toBeGreaterThan(0);
    expect(screen.getByText('0001')).toBeTruthy();
    expect(screen.getByText('xxxx1')).toBeTruthy();
    expect(screen.getByText('0002')).toBeTruthy();
    expect(screen.getAllByText('--').length).toBeGreaterThan(0);
  });

  it('集成详情事件表使用同一身份列并为空 cmdb_id 显示占位符', () => {
    const event = {
      id: 1,
      start_time: '',
      end_time: '',
      source_name: 'NATS',
      raw_data: {},
      received_at: '',
      title: 'CPU high',
      description: '',
      level: '2',
      action: 'created',
      rule_id: null,
      event_id: 'event-1',
      external_id: 'external-1',
      item: 'cpu_usage',
      resource_id: '0001',
      resource_type: '主机',
      resource_name: 'ip1',
      monitor_id: '0001',
      cmdb_id: null,
      status: 'new',
      value: 81,
    } as EventTableItem;

    renderWithIntl(
      <EventTable
        dataSource={[event]}
        pagination={{ current: 1, pageSize: 20, total: 1 }}
        onChange={() => undefined}
      />
    );

    expect(screen.getAllByText('监控实例 ID').length).toBeGreaterThan(0);
    expect(screen.getAllByText('CMDB 实例 ID').length).toBeGreaterThan(0);
    expect(screen.getByText('0001')).toBeTruthy();
    expect(screen.getAllByText('--').length).toBeGreaterThan(0);
  });
});
