import { describe, expect, test } from 'vitest';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import { buildRelativeTimeRangeFilterValue } from '@/app/ops-analysis/utils/filterValue';
import { buildFilterConfigConfirmSnapshot } from '@/app/ops-analysis/utils/unifiedFilterState';
import { buildWidgetRequestParams } from '@/app/ops-analysis/utils/widgetDataTransform';

const TIME_ID = 'time__timeRange';

const timeDefinition = (
  defaultValue: FilterValue,
  extra?: Partial<UnifiedFilterDefinition>,
): UnifiedFilterDefinition => ({
  id: TIME_ID,
  key: 'time',
  name: '时间范围',
  type: 'timeRange',
  defaultValue,
  order: 0,
  enabled: true,
  ...extra,
});

const confirmTime = (
  previous: UnifiedFilterDefinition,
  next: UnifiedFilterDefinition,
  current: FilterValue,
) =>
  buildFilterConfigConfirmSnapshot(
    [next],
    { [TIME_ID]: current },
    { [TIME_ID]: current },
    [previous],
  );

describe('buildFilterConfigConfirmSnapshot default override', () => {
  test('timeRange 仍停在旧相对默认时，确认后改用新默认，忽略 start/end 毫秒差', () => {
    const previousDefault = buildRelativeTimeRangeFilterValue(
      360,
      '2026-09-22T02:00:00.000Z',
    );
    const runtimeValue = buildRelativeTimeRangeFilterValue(
      360,
      '2026-09-22T02:00:00.001Z',
    );
    const nextDefault = buildRelativeTimeRangeFilterValue(
      15,
      '2026-09-22T02:33:00.000Z',
    );

    const snapshot = confirmTime(
      timeDefinition(previousDefault),
      timeDefinition(nextDefault),
      runtimeValue,
    );

    expect(snapshot.filterValues[TIME_ID]).toMatchObject({ selectValue: 15 });
    expect(snapshot.appliedFilterValues[TIME_ID]).toMatchObject({
      selectValue: 15,
    });

    const request = buildWidgetRequestParams({
      config: {
        chartType: 'single',
        dataSource: 1,
        dataSourceParams: [
          {
            name: 'time',
            type: 'timeRange',
            filterType: 'filter',
            value: 360,
          },
        ],
        filterBindings: { [TIME_ID]: true },
      },
      unifiedFilterValues: snapshot.appliedFilterValues,
      filterBindings: { [TIME_ID]: true },
      filterDefinitions: snapshot.definitions,
    });
    expect(request).toEqual({ time: { selectValue: 15 } });
  });

  test('timeRange 已被改成其它快捷区间时，确认不覆盖', () => {
    const customized = buildRelativeTimeRangeFilterValue(
      60,
      '2026-09-22T01:00:00.000Z',
    );
    const snapshot = confirmTime(
      timeDefinition(buildRelativeTimeRangeFilterValue(360, '2026-09-22T00:00:00.000Z')),
      timeDefinition(buildRelativeTimeRangeFilterValue(15, '2026-09-22T02:00:00.000Z')),
      customized,
    );

    expect(snapshot.filterValues[TIME_ID]).toEqual(customized);
    expect(snapshot.appliedFilterValues[TIME_ID]).toEqual(customized);
  });

  test('只改名称、默认值语义没变时，不重写当前相对时间', () => {
    const runtimeValue = buildRelativeTimeRangeFilterValue(
      360,
      '2026-09-22T02:00:00.000Z',
    );
    const snapshot = confirmTime(
      timeDefinition(
        buildRelativeTimeRangeFilterValue(360, '2026-09-22T01:00:00.000Z'),
        { name: '时间' },
      ),
      timeDefinition(
        buildRelativeTimeRangeFilterValue(360, '2026-09-22T03:00:00.000Z'),
        { name: '查询时间' },
      ),
      runtimeValue,
    );

    expect(snapshot.filterValues[TIME_ID]).toEqual(runtimeValue);
  });

  test('字符串当前值仍是旧默认时才换成新默认', () => {
    const previous: UnifiedFilterDefinition = {
      id: 'env__string',
      key: 'env',
      name: '环境',
      type: 'string',
      defaultValue: 'prod',
      order: 0,
      enabled: true,
    };
    const next = { ...previous, defaultValue: 'dev' };

    const stillOnDefault = buildFilterConfigConfirmSnapshot(
      [next],
      { env__string: 'prod' },
      { env__string: 'prod' },
      [previous],
    );
    expect(stillOnDefault.filterValues.env__string).toBe('dev');

    const customized = buildFilterConfigConfirmSnapshot(
      [next],
      { env__string: 'staging' },
      { env__string: 'staging' },
      [previous],
    );
    expect(customized.filterValues.env__string).toBe('staging');
  });

  test('组织筛选项即使默认值变了也不覆盖当前值', () => {
    const previous: UnifiedFilterDefinition = {
      id: 'organization__string',
      key: 'organization',
      name: '组织',
      type: 'string',
      inputMode: 'organization',
      defaultValue: '1',
      order: 0,
      enabled: true,
    };
    const next = { ...previous, defaultValue: '99' };
    const snapshot = buildFilterConfigConfirmSnapshot(
      [next],
      { organization__string: '1' },
      { organization__string: '1' },
      [previous],
    );

    expect(snapshot.filterValues.organization__string).toBe('1');
  });

  test('dateRange 仍停在旧默认时换成新默认，自定义区间不覆盖', () => {
    const previous: UnifiedFilterDefinition = {
      id: 'period__dateRange',
      key: 'period',
      name: '账期',
      type: 'dateRange',
      defaultValue: { rangeType: 'last_7_days' },
      order: 0,
      enabled: true,
    };
    const next = {
      ...previous,
      defaultValue: { rangeType: 'last_30_days' as const },
    };

    const stillOnDefault = buildFilterConfigConfirmSnapshot(
      [next],
      { period__dateRange: { rangeType: 'last_7_days' } },
      { period__dateRange: { rangeType: 'last_7_days' } },
      [previous],
    );
    expect(stillOnDefault.filterValues.period__dateRange).toEqual({
      rangeType: 'last_30_days',
    });

    const custom = { rangeType: 'custom' as const, startDate: '2026-08-01', endDate: '2026-08-17' };
    const customized = buildFilterConfigConfirmSnapshot(
      [next],
      { period__dateRange: custom },
      { period__dateRange: custom },
      [previous],
    );
    expect(customized.filterValues.period__dateRange).toEqual(custom);
  });

  test('顶部筛选已改但未查询时，不把已应用查询改成新默认', () => {
    const previous = timeDefinition(
      buildRelativeTimeRangeFilterValue(360, '2026-09-22T00:00:00.000Z'),
    );
    const next = timeDefinition(
      buildRelativeTimeRangeFilterValue(15, '2026-09-22T02:00:00.000Z'),
    );
    const pendingBarValue = buildRelativeTimeRangeFilterValue(
      60,
      '2026-09-22T01:00:00.000Z',
    );
    const appliedValue = buildRelativeTimeRangeFilterValue(
      360,
      '2026-09-22T00:00:00.001Z',
    );

    const snapshot = buildFilterConfigConfirmSnapshot(
      [next],
      { [TIME_ID]: pendingBarValue },
      { [TIME_ID]: appliedValue },
      [previous],
    );

    expect(snapshot.filterValues[TIME_ID]).toEqual(pendingBarValue);
    expect(snapshot.appliedFilterValues[TIME_ID]).toEqual(appliedValue);
  });
});
