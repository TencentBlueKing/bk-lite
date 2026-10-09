import { describe, expect, it } from 'vitest';

import type { ChartData } from '@/app/monitor/types';
import { calculateMetrics } from '@/app/monitor/utils/common';
import { transformToFrontendFormat } from '../savedQueryDrawer';
import {
  applySearchPresentationToAll,
  buildSearchChartTable,
  defaultSearchTableKind,
  readSavedChartPresentation,
  resolveSearchRange,
  resolveSearchTableKind,
  isSearchSeriesActive,
  seedSearchChartPresentation,
  placeFrozenSampleSeries,
  toCsv,
  toneForExtreme,
  toggleEmphasizedSeries,
  emptySearchChartPresentation,
  writeSavedChartPresentation
} from '../searchChartPresentation';

const point = (
  time: number,
  values: Record<string, number | null>,
  details?: ChartData['details']
): ChartData => ({
  time,
  ...values,
  details
});

describe('search chart presentation', () => {
  const data: ChartData[] = [
    point(10, { value1: 2, value2: null }, {
      value1: [{ name: 'instance_name', label: 'Instance', value: 'web-01' }],
      value2: [{ name: 'instance_name', label: 'Instance', value: 'web-02' }]
    }),
    point(20, { value1: 4, value2: 8 }),
    point(30, { value1: 6, value2: 5 })
  ];

  it('按时间对齐序列，缺口保持空值，统计与折线图同一套有效值', () => {
    const model = buildSearchChartTable(data);
    const first = model.series.find((item) => item.key === 'value1');
    const second = model.series.find((item) => item.key === 'value2');
    const summary = calculateMetrics(
      data as Record<string, number | null | undefined>[],
      'value1'
    );

    expect(model.times).toEqual([10, 20, 30]);
    expect(first).toMatchObject({
      identifier: 'Instance: web-01',
      values: [2, 4, 6],
      min: summary.minValue,
      max: summary.maxValue,
      avg: summary.avgValue,
      latest: 6,
      range: 4
    });
    expect(second?.values).toEqual([null, 8, 5]);
    expect(second?.latest).toBe(5);
    expect(second?.range).toBe(3);
  });

  it('极差按表格上的最大值和最小值相减', () => {
    const model = buildSearchChartTable([
      point(1, { value1: 2.466 }),
      point(2, { value1: 6.104 })
    ]);
    expect(model.series[0]?.range).toBe(3.63);
    expect(resolveSearchRange(6.104, 2.466)).toBe(3.63);
    expect(resolveSearchRange(null, 1)).toBeNull();
  });

  it('两条及以上默认序列对比，只有一条默认采样明细', () => {
    expect(defaultSearchTableKind(4)).toBe('compare');
    expect(defaultSearchTableKind(1)).toBe('samples');
    expect(defaultSearchTableKind(0)).toBe('samples');
    expect(
      resolveSearchTableKind(
        { view: 'combo', tableKind: 'samples', emphasizedKeys: [] },
        4
      )
    ).toBe('samples');
  });

  it('刷新保留已选读法，新查询才读取保存的读法', () => {
    const kept = seedSearchChartPresentation(
      {
        a: { view: 'combo', tableKind: 'samples', emphasizedKeys: ['value2'] }
      },
      [{ id: 'a', viewMode: 'line', tableKind: null }]
    );
    expect(kept.a.view).toBe('combo');
    expect(kept.a.emphasizedKeys).toEqual(['value2']);

    const loaded = seedSearchChartPresentation(
      {},
      [{ id: 'b', viewMode: 'table', tableKind: 'samples' }]
    );
    expect(loaded.b).toEqual({
      view: 'combo',
      tableKind: 'samples',
      emphasizedKeys: null
    });
    expect(readSavedChartPresentation({ view_mode: 'grid' }).view).toBe('combo');
  });

  it('未写读法时默认图表，选了折线会单独记下来', () => {
    expect(emptySearchChartPresentation().view).toBe('combo');
    expect(writeSavedChartPresentation('line', null)).toEqual({
      view_mode: 'line'
    });
    expect(writeSavedChartPresentation('combo', 'compare')).toEqual({
      view_mode: 'combo',
      table_kind: 'compare'
    });

    const [group] = transformToFrontendFormat([
      {
        id: 'saved-1',
        name: '历史查询',
        object: 1,
        plugin: 2,
        instance_ids: ['i1'],
        metric: 3,
        aggregation: 'AVG',
        conditions: [],
        view_mode: 'combo',
        table_kind: 'compare'
      }
    ]);
    expect(group.viewMode).toBe('combo');
    const [legacyTable] = transformToFrontendFormat([
      {
        id: 'saved-table',
        name: '旧表格',
        object: 1,
        plugin: 2,
        instance_ids: [],
        metric: 3,
        aggregation: 'AVG',
        conditions: [],
        view_mode: 'table'
      }
    ]);
    expect(legacyTable.viewMode).toBe('combo');
    expect(group.tableKind).toBe('compare');

    const [legacy] = transformToFrontendFormat([
      {
        id: 'saved-2',
        name: '旧查询',
        object: 1,
        plugin: 2,
        instance_ids: [],
        metric: 3,
        aggregation: 'AVG',
        conditions: []
      }
    ]);
    expect(legacy.viewMode).toBe('combo');
    expect(legacy.tableKind).toBeNull();
  });

  it('全部用这个同步读法，并保留每张卡自己的突出序列', () => {
    const next = applySearchPresentationToAll(
      {
        a: { view: 'line', tableKind: null, emphasizedKeys: ['value1'] },
        b: { view: 'line', tableKind: null, emphasizedKeys: null }
      },
      ['a', 'b'],
      { view: 'combo', tableKind: 'samples', emphasizedKeys: ['value9'] }
    );
    expect(next.a).toEqual({
      view: 'combo',
      tableKind: 'samples',
      emphasizedKeys: ['value1']
    });
    expect(next.b.emphasizedKeys).toBeNull();
    expect(toggleEmphasizedSeries(['value1'], 'value1')).toBeNull();
    expect(toggleEmphasizedSeries(null, 'value2')).toEqual(['value2']);
    expect(toggleEmphasizedSeries([], 'value2')).toEqual(['value2']);
    expect(toggleEmphasizedSeries(['value2'], 'value1')).toEqual(['value2', 'value1']);
    expect(isSearchSeriesActive(null, 'value1')).toBe(true);
    expect(isSearchSeriesActive([], 'value1')).toBe(false);
    expect(isSearchSeriesActive(['value2'], 'value1')).toBe(false);
    expect(isSearchSeriesActive(['value1', 'value2'], 'value1')).toBe(true);
  });

  it('导出 CSV 带 BOM，并转义逗号和引号', () => {
    const csv = toCsv(
      ['标识', '最新值'],
      [['Instance: web-01', '3.10 %'], ['a, "b"', '1.00']]
    );
    expect(csv.startsWith('\uFEFF')).toBe(true);
    expect(csv.slice(1)).toBe('标识,最新值\nInstance: web-01,3.10 %\n"a, ""b""",1.00');
  });

  it('只给一组里的最高和最低染色，相等时不染', () => {
    expect(toneForExtreme(9, [3, 9, 5])).toBe('high');
    expect(toneForExtreme(3, [3, 9, 5])).toBe('low');
    expect(toneForExtreme(5, [3, 9, 5])).toBeNull();
    expect(toneForExtreme(9, [9, 9])).toBeNull();
    expect(toneForExtreme(null, [1, 2])).toBeNull();
    expect(toneForExtreme(4, [4, 4, null])).toBeNull();
    expect(toneForExtreme(2, [2, 9, 2])).toBe('low');
  });

  it('冻结另一列时，原来的冻结列回到原位', () => {
    const series = [{ key: 'a' }, { key: 'b' }, { key: 'c' }];
    expect(placeFrozenSampleSeries(series, null).map((item) => item.key)).toEqual([
      'a',
      'b',
      'c'
    ]);
    expect(placeFrozenSampleSeries(series, 'c').map((item) => item.key)).toEqual([
      'c',
      'a',
      'b'
    ]);
    expect(placeFrozenSampleSeries(series, 'b').map((item) => item.key)).toEqual([
      'b',
      'a',
      'c'
    ]);
    expect(placeFrozenSampleSeries(series, 'missing').map((item) => item.key)).toEqual([
      'a',
      'b',
      'c'
    ]);
  });
});
