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
  default: () => null
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

    const sparks = view.container.querySelectorAll('svg.focusSpark');
    expect(sparks).toHaveLength(3);
    expect(Array.from(sparks).map((node) => node.getAttribute('width'))).toEqual(['110', '110', '110']);
    expect(Array.from(sparks).map((node) => node.querySelector('polyline')?.getAttribute('stroke'))).toEqual([
      '#722ED1',
      '#13C2C2',
      '#00B42A'
    ]);
    sparks.forEach((node) => {
      expect(node.querySelector('polyline')?.getAttribute('points')?.split(' ').length).toBeGreaterThan(1);
    });
    expect(view.container.querySelectorAll('.shortcutCard svg')).toHaveLength(3);
  });
});
