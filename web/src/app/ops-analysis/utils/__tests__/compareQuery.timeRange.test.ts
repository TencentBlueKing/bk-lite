import { describe, expect, it } from 'vitest';

import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { ParamItem } from '@/app/ops-analysis/types/dataSource';
import {
  buildCompareRequestParams,
  fetchCompareData,
} from '@/app/ops-analysis/utils/compareQuery';

const NOW = '2026-07-17T03:08:00.000Z';
const CURRENT = ['2026-07-17T02:08:00.000Z', NOW];
const BASELINE = ['2026-07-17T01:08:00.000Z', '2026-07-17T02:08:00.000Z'];
const resolutionContext = {
  referenceNow: NOW,
  timezone: 'Asia/Shanghai',
};

const timeParam = (value: ParamItem['value'], filterType: ParamItem['filterType'] = 'params'): ParamItem => ({
  name: 'time_range',
  alias_name: '时间范围',
  type: 'timeRange',
  filterType,
  value,
});

const timeDefinition: UnifiedFilterDefinition = {
  id: 'time_range__timeRange',
  key: 'time_range',
  name: '时间范围',
  type: 'timeRange',
  enabled: true,
  order: 0,
  defaultValue: 60,
};

describe('timeRange period compare', () => {
  it('keeps a relative shortcut as selectValue when compare is off', () => {
    const request = buildCompareRequestParams({
      config: {
        compare: false,
        dataSourceParams: [timeParam(60)],
      },
      resolutionContext,
    });

    expect(request.currentParams).toEqual({ time_range: { selectValue: 60 } });
    expect(request.baselineParams).toBeNull();
  });

  it('expands both windows from one instant when compare is on', () => {
    const request = buildCompareRequestParams({
      config: {
        compare: true,
        dataSourceParams: [timeParam(60)],
      },
      resolutionContext,
    });

    expect(request.currentParams).toEqual({ time_range: CURRENT });
    expect(request.baselineParams).toEqual({ time_range: BASELINE });
  });

  it('ignores stale start and end stored with the shortcut', async () => {
    const calls: unknown[] = [];
    const result = await fetchCompareData({
      dataSourceId: 81,
      config: {
        compare: true,
        dataSourceParams: [timeParam(60, 'filter')],
      },
      unifiedFilterValues: {
        'time_range__timeRange': {
          selectValue: 60,
          start: '2020-01-01T00:00:00.000Z',
          end: '2020-01-01T01:00:00.000Z',
        },
      },
      filterBindings: { 'time_range__timeRange': true },
      filterDefinitions: [timeDefinition],
      resolutionContext,
      getSourceDataByApiId: async (_id, params) => {
        calls.push(params);
        return { data: { value: 1 }, warnings: [] };
      },
    });

    expect(calls).toEqual([
      { time_range: CURRENT },
      { time_range: BASELINE },
    ]);
    expect(result.currentData).toEqual({ value: 1 });
    expect(result.baselineData).toEqual({ value: 1 });
  });

  it('shifts a custom range by its own length', async () => {
    const calls: unknown[] = [];
    await fetchCompareData({
      dataSourceId: 81,
      config: {
        compare: true,
        dataSourceParams: [timeParam(60, 'filter')],
      },
      unifiedFilterValues: {
        'time_range__timeRange': {
          selectValue: 0,
          start: '2026-08-19T00:00:00.000Z',
          end: '2026-08-20T00:00:00.000Z',
        },
      },
      filterBindings: { 'time_range__timeRange': true },
      filterDefinitions: [timeDefinition],
      resolutionContext,
      getSourceDataByApiId: async (_id, params) => {
        calls.push(params);
        return { data: { value: 1 }, warnings: [] };
      },
    });

    expect(calls).toEqual([
      { time_range: ['2026-08-19T00:00:00.000Z', '2026-08-20T00:00:00.000Z'] },
      { time_range: ['2026-08-18T00:00:00.000Z', '2026-08-19T00:00:00.000Z'] },
    ]);
  });
});
