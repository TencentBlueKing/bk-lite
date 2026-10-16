import React from 'react';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { EntityTableRow } from '../entity-series';

vi.mock('./layered.module.scss', () => ({
  default: new Proxy({}, { get: (_target, key) => String(key) })
}));

vi.mock('../index.module.scss', () => ({
  default: new Proxy({}, { get: (_target, key) => String(key) })
}));

vi.mock('../../../shared/utils/content-i18n', () => ({
  useDashboardText: () => ({
    t: (_id: string, fallback?: string, values?: Record<string, string | number>) => {
      if (!fallback) return _id;
      if (!values) return fallback;
      return fallback.replace(/\{(\w+)\}/g, (_match, key: string) => String(values[key] ?? ''));
    }
  })
}));

vi.mock('./thin-time-series', () => ({
  default: (props: {
    title?: string;
    unit?: string;
    bare?: boolean;
    className?: string;
    data?: unknown[];
    legends?: Array<{ label: string; color: string }>;
  }) => (
    <div
      data-chart="1"
      data-title={props.title || ''}
      data-unit={props.unit || ''}
      data-bare={props.bare ? '1' : '0'}
      data-class={props.className || ''}
      data-points={String(props.data?.length || 0)}
      data-legends={String(props.legends?.length || 0)}
      data-color={props.legends?.[0]?.color || ''}
      data-label={props.legends?.[0]?.label || ''}
    />
  )
}));

vi.mock('./events-rail', () => ({
  default: () => null
}));

import OverviewPane from './overview-pane';

const row = (
  key: string,
  labels: Record<string, string>,
  values: Record<string, number | null>,
  series: EntityTableRow['series']
): EntityTableRow => ({ key, labels, values, series });

describe('overview focus sparks', () => {
  it('draws one spark per focus card from that object series', () => {
    const disk = row(
      'mount-root',
      { path: '/' },
      { disk_used_percent: 86.2 },
      { disk_used_percent: [
        { time: 1, value: 62 }, { time: 2, value: 64 }, { time: 3, value: 71 },
        { time: 4, value: 78 }, { time: 5, value: 86.2 }
      ] }
    );
    const nic = row(
      'nic-eth0',
      { interface: 'eth0' },
      { net_bytes_recv_rate: 100, net_bytes_sent_rate: 50 },
      {
        net_bytes_recv_rate: [
          { time: 1, value: 40 }, { time: 2, value: 70 }, { time: 3, value: 55 },
          { time: 4, value: 90 }, { time: 5, value: 100 }
        ],
        net_bytes_sent_rate: [
          { time: 1, value: 10 }, { time: 2, value: 20 }, { time: 3, value: 15 },
          { time: 4, value: 30 }, { time: 5, value: 50 }
        ]
      }
    );
    const process = row(
      'proc-java',
      { process_name: 'java' },
      { process_cpu_usage: 41.8 },
      { process_cpu_usage: [
        { time: 1, value: 18 }, { time: 2, value: 28 }, { time: 3, value: 22 },
        { time: 4, value: 36 }, { time: 5, value: 41.8 }
      ] }
    );

    const view = render(
      <OverviewPane
        metrics={{}}
        loading={false}
        diskRows={[disk]}
        diskLoading={false}
        netRows={[nic]}
        processRows={[process]}
        processReady
        alertCount={0}
        onJump={() => undefined}
        alerts={{ cpu: 'none', mem: 'none', disk: 'none', load: 'none', uptime: 'none' }}
      />
    );

    expect(view.getByText('最满挂载点')).toBeTruthy();
    expect(view.getByText('吞吐最高网卡')).toBeTruthy();
    expect(view.getByText('CPU 占用最高')).toBeTruthy();
    expect(view.getByText('/')).toBeTruthy();
    expect(view.getByText('eth0')).toBeTruthy();
    expect(view.getByText('java')).toBeTruthy();

    const charts = Array.from(view.container.querySelectorAll('[data-class="focusChart"]'));
    expect(charts).toHaveLength(3);
    expect(charts.map((node) => node.getAttribute('data-bare'))).toEqual(['1', '1', '1']);
    expect(charts.map((node) => node.getAttribute('data-title'))).toEqual(['', '', '']);
    expect(charts.map((node) => node.getAttribute('data-legends'))).toEqual(['1', '1', '1']);
    expect(charts.map((node) => node.getAttribute('data-unit'))).toEqual(['percent', 'byteps', 'percent']);
    expect(charts.map((node) => node.getAttribute('data-color'))).toEqual([
      '#722ED1',
      '#13C2C2',
      '#00B42A'
    ]);
    charts.forEach((node) => {
      expect(Number(node.getAttribute('data-points'))).toBe(5);
    });
    expect(view.container.querySelector('svg')).toBeNull();
  });

  it('passes the object series through to the line chart', () => {
    const dense = Array.from({ length: 240 }, (_, index) => ({
      time: index,
      value: index % 2 === 0 ? 10 : 90
    }));
    const disk = row('mount-root', { path: '/' }, { disk_used_percent: 90 }, {
      disk_used_percent: dense
    });
    const view = render(
      <OverviewPane
        metrics={{}}
        loading={false}
        diskRows={[disk]}
        diskLoading={false}
        netRows={[]}
        processRows={[]}
        processReady={false}
        alertCount={0}
        onJump={() => undefined}
        alerts={{ cpu: 'none', mem: 'none', disk: 'none', load: 'none', uptime: 'none' }}
      />
    );
    const chart = view.container.querySelector('[data-class="focusChart"]');
    expect(chart?.getAttribute('data-points')).toBe('240');
    expect(chart?.getAttribute('data-color')).toBe('#722ED1');
    expect(chart?.getAttribute('data-legends')).toBe('1');
  });
});
