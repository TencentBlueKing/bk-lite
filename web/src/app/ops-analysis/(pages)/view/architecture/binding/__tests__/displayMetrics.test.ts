import { describe, expect, it } from 'vitest';
import {
  buildNodeMetricCards,
  collectMetricUuids,
  combineMetricBatches,
  formatMetricText,
  metricCardLines,
  visibleColumns,
  type MetricColumn,
} from '../displayMetrics';

const columns: MetricColumn[] = [
  { name: 'IP', keys: ['field::os::host::ip'] },
  { name: 'CPU使用率', keys: ['os::cpu_usage_total'] },
  { name: '内存使用率', keys: ['os::mem_used_percent'] },
  { name: '磁盘使用率', keys: ['os::disk_used_percent'] },
  { name: '网络入向吞吐', keys: ['os::net_bytes_recv_rate'] },
];

describe('architecture display metrics', () => {
  it('shows nothing until the user selects columns, and skips attribute columns', () => {
    expect(visibleColumns(columns, undefined)).toEqual([]);
    expect(visibleColumns(columns, {
      mode: 'custom',
      keys: ['os::cpu_usage_total', 'field::os::host::ip', 'os::net_bytes_recv_rate'],
    }).map((column) => column.name)).toEqual(['CPU使用率', '网络入向吞吐']);
  });

  it('keeps a missing value as a dash and does not substitute another metric', () => {
    const lines = metricCardLines(
      columns,
      {
        'os::mem_used_percent': { value: '40', unit: '%' },
      },
      { mode: 'custom', keys: ['os::cpu_usage_total', 'os::mem_used_percent'] },
    );
    expect(lines.map((line) => line.text)).toEqual(['—', '40.00 %']);
  });

  it('colors a pinned value when an active alert matches that metric', () => {
    const lines = metricCardLines(
      columns,
      {
        'os::cpu_usage_total': { value: '86.5', unit: '%' },
        'os::mem_used_percent': { value: '52', unit: '%' },
      },
      { mode: 'custom', keys: ['os::cpu_usage_total', 'os::mem_used_percent'] },
      [{ content: '主机 CPU 使用率过高', level: 'warning', metric_name: 'CPU Usage', metric_key: 'cpu_usage_total' }],
    );
    expect(lines[0]).toEqual({ name: 'CPU使用率', text: '86.50 %', tone: 'warning' });
    expect(lines[1]).toEqual({ name: '内存使用率', text: '52.00 %' });
  });

  it('does not request nodes that have no selection', () => {
    const views = [{
      items: [
        { id: 'unset', bkBinding: { inst_uuid: 'u-unset', model_id: 'host' } },
        {
          id: 'picked',
          bkBinding: { inst_uuid: 'u-picked', model_id: 'host' },
          bkDisplayMetrics: { mode: 'custom', keys: ['os::cpu_usage_total'] },
        },
      ],
    }];
    expect(collectMetricUuids(views)).toEqual(['u-picked']);
    const cards = buildNodeMetricCards(
      views,
      {
        'u-unset': {
          inst_uuid: 'u-unset',
          monitor_object_id: '12',
          values: { 'os::cpu_usage_total': { value: 9, unit: '%' } },
        },
        'u-picked': {
          inst_uuid: 'u-picked',
          monitor_object_id: '12',
          values: { 'os::cpu_usage_total': { value: 1, unit: '%' } },
        },
      },
      { '12': { columns } },
    );
    expect(Object.keys(cards)).toEqual(['picked']);
    expect(cards.picked.lines[0]).toEqual({ name: 'CPU使用率', text: '1.00 %' });
  });

  it('drops a node that the latest batch no longer returns', () => {
    const previous = {
      'u-1': {
        inst_uuid: 'u-1',
        monitor_object_id: '12',
        values: {},
      },
    };
    const combined = combineMetricBatches(
      [{ uuids: ['u-1'], ok: true, data: { objects: {}, items: [] } }],
      previous,
    );
    expect(combined.byUuid).toEqual({});
  });

  it('formats values the same way as the monitor module', () => {
    expect(formatMetricText({ value: 29.147999999999996, unit: '%' })).toBe('29.15 %');
    expect(formatMetricText({ value: '67.664', unit: '%' })).toBe('67.66 %');
    expect(formatMetricText({ value: '148.0', unit: '' })).toBe('148');
    expect(formatMetricText({ value: 148, unit: 'counts' })).toBe('148');
    expect(formatMetricText({ value: 91.9428277346197, unit: '' })).toBe('91.94');
    expect(formatMetricText({ value: 45.071191386730986, unit: 'cps' })).toBe('45.07 cps');
    expect(formatMetricText({ value: 107.9332638623795, unit: 'cps' })).toBe('107.93 cps');
    expect(formatMetricText({ value: 98.304, unit: '%' })).toBe('98.30 %');
  });
});
