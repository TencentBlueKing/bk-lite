import { describe, expect, it } from 'vitest';
import {
  buildNodeMetricCards,
  collectMetricUuids,
  combineMetricBatches,
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
    expect(lines.map((line) => line.text)).toEqual(['—', '40 %']);
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
    expect(cards.picked.lines[0]).toEqual({ name: 'CPU使用率', text: '1 %' });
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
});
