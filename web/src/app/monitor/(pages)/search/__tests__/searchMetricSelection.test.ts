import { describe, expect, it } from 'vitest';

import type { MetricItem } from '@/app/monitor/types';
import type { QueryGroup } from '@/app/monitor/types/search';
import { transformToFrontendFormat } from '../savedQueryDrawer';
import { collectMetricIdsByResource } from '../savedQueryMetricMerge';
import {
  buildSearchQueryParams,
  expandSearchCards,
  intersectMetricDimensionLabels,
  listSelectedMetricIds,
  readSavedMetricSelection,
  writeSavedMetricIds
} from '../searchQueryLogic';

const metric = (
  id: number,
  dimensions: string[],
  unit = '%'
): MetricItem =>
  ({
    id,
    name: `metric_${id}`,
    display_name: `指标${id}`,
    unit,
    dimensions
  }) as MetricItem;

const group = (patch: Partial<QueryGroup>): QueryGroup => ({
  id: 'g1',
  name: '查询条件 1',
  object: 8,
  plugin: 6,
  instanceIds: ['host-1'],
  metric: null,
  aggregation: 'AVG',
  conditions: [],
  collapsed: false,
  ...patch
});

describe('指标多选', () => {
  it('单个历史 ID 和数组都能读成多选，保存时写成数组', () => {
    expect(listSelectedMetricIds(301)).toEqual([301]);
    expect(listSelectedMetricIds(['301', 302, 301])).toEqual([301, 302]);
    expect(readSavedMetricSelection('cpu_usage').legacyMetricName).toBe(
      'cpu_usage'
    );
    expect(readSavedMetricSelection('cpu_usage').metric).toEqual([]);
    expect(writeSavedMetricIds(301)).toEqual([301]);
    expect(writeSavedMetricIds([301, 302])).toEqual([301, 302]);

    const [loaded] = transformToFrontendFormat([
      {
        id: 'saved',
        name: '多指标',
        object: 8,
        plugin: 6,
        instance_ids: ['host-1'],
        metric: [301, 302],
        aggregation: 'AVG',
        conditions: []
      }
    ]);
    expect(loaded.metric).toEqual([301, 302]);
  });

  it('一组里的每个指标各拆一张卡，并各自带上自己的单位', () => {
    const cards = expandSearchCards([
      group({ metric: [301, 302] }),
      group({ id: 'g2', metric: 303, instanceIds: [] })
    ]);
    expect(cards.map((card) => card.cardId)).toEqual(['g1:301', 'g1:302']);

    const cpu = buildSearchQueryParams({
      group: group({
        metric: [301, 302],
        conditions: [
          { label: 'mount', condition: '=', value: '/' },
          { label: 'cpu', condition: '=', value: 'cpu-total' }
        ]
      }),
      metrics: [metric(301, ['mount'], '%'), metric(302, ['mount', 'cpu'], 'B')],
      instances: [
        {
          instance_id: 'host-1',
          instance_name: 'host-1',
          instance_id_values: ['host-1']
        }
      ],
      timeRange: { timeRange: [1000, 2000], originValue: 0 },
      metricId: 301
    });
    expect(cpu.metric_id).toBe(301);
    expect(cpu.source_unit).toBe('%');
    expect(cpu.filters).toEqual([
      { label: 'mount', operator: '=', value: '/' }
    ]);

    const single = buildSearchQueryParams({
      group: group({
        metric: 301,
        conditions: [{ label: 'mount', condition: '=', value: '/' }]
      }),
      metrics: [metric(301, ['mount'])],
      instances: [
        {
          instance_id: 'host-1',
          instance_name: 'host-1',
          instance_id_values: ['host-1']
        }
      ],
      timeRange: { timeRange: [1000, 2000], originValue: 0 }
    });
    expect(single.metric_id).toBe(301);
    expect(single.filters).toEqual([
      { label: 'mount', operator: '=', value: '/' }
    ]);
  });

  it('筛选标签取已选指标维度的交集，加载时收集组内全部指标', () => {
    expect(
      intersectMetricDimensionLabels([
        metric(301, ['mount', 'cpu']),
        metric(302, ['mount'])
      ])
    ).toEqual(['mount']);

    const collected = collectMetricIdsByResource(
      [group({ metric: [301, 302] }), group({ id: 'g2', metric: 303 })],
      (objectId, pluginId) => `${objectId}_${pluginId}`
    );
    expect(collected.get('8_6')?.metricIds).toEqual([301, 302, 303]);
  });
});
