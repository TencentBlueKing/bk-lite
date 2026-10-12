import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, test } from 'vitest';

import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import {
  getUnifiedFilterTimeSelectorDefaultValue,
  normalizeTimeRangeFilterValue,
} from '@/app/ops-analysis/utils/filterValue';
import {
  applyChangedDefaultsIfStillOnPrevious,
  buildResetFilterValues,
  recomputeTimeRangeValuesFromDefaults,
} from '@/app/ops-analysis/utils/unifiedFilterState';
import { buildWidgetRequestParams } from '@/app/ops-analysis/utils/widgetDataTransform';

const REFERENCE = '2026-10-09T00:00:00.000Z';
const TIME_ID = 'time__timeRange';

const timeDefinition = (
  defaultValue: UnifiedFilterDefinition['defaultValue'],
): UnifiedFilterDefinition => ({
  id: TIME_ID,
  key: 'time',
  name: '时间范围',
  type: 'timeRange',
  defaultValue,
  order: 0,
  enabled: true,
});

const legacyDefault = { selectValue: 360, rangePickerVaule: null };

describe('normalizeTimeRangeFilterValue', () => {
  test('selectValue>0 不要求 start/end，按相对时间处理', () => {
    const normalized = normalizeTimeRangeFilterValue(legacyDefault, REFERENCE);
    expect(normalized).toEqual({
      selectValue: 360,
      start: '2026-10-08T18:00:00.000Z',
      end: REFERENCE,
    });
  });

  test('正整数分钟同样按相对时间处理', () => {
    expect(normalizeTimeRangeFilterValue(10080, REFERENCE)).toMatchObject({
      selectValue: 10080,
    });
  });

  test('selectValue 为 0 且有起止时保留绝对区间', () => {
    expect(normalizeTimeRangeFilterValue({
      selectValue: 0,
      start: '2026-10-01T00:00:00.000Z',
      end: '2026-10-02T00:00:00.000Z',
    })).toEqual({
      selectValue: 0,
      start: '2026-10-01T00:00:00.000Z',
      end: '2026-10-02T00:00:00.000Z',
    });
  });

  test('空值和无法识别的结构返回 null', () => {
    expect(normalizeTimeRangeFilterValue(null)).toBeNull();
    expect(normalizeTimeRangeFilterValue({ rangePickerVaule: null })).toBeNull();
  });
});

describe('统一筛选时间默认展示', () => {
  test('旧 YAML 默认值在配置弹窗和筛选栏都显示 N 分钟，而不是 15 分钟', () => {
    expect(getUnifiedFilterTimeSelectorDefaultValue(legacyDefault, REFERENCE)).toEqual({
      selectValue: 360,
      rangePickerVaule: null,
    });
    expect(getUnifiedFilterTimeSelectorDefaultValue(null)).toEqual({
      selectValue: 15,
      rangePickerVaule: null,
    });
  });

  test('绝对区间仍交给范围选择器', () => {
    const value = getUnifiedFilterTimeSelectorDefaultValue({
      selectValue: 0,
      start: '2026-10-01T00:00:00.000Z',
      end: '2026-10-02T00:00:00.000Z',
    });
    expect(value.selectValue).toBe(0);
    expect(value.rangePickerVaule?.map((item) => item.toISOString())).toEqual([
      '2026-10-01T00:00:00.000Z',
      '2026-10-02T00:00:00.000Z',
    ]);
  });
});

describe('buildResetFilterValues timeRange', () => {
  test('重置把旧格式默认值归一成相对时间，请求与展示一致', () => {
    const definition = timeDefinition(legacyDefault);
    const resetValues = buildResetFilterValues([definition]);
    const resetTime = resetValues[TIME_ID];
    expect(resetTime).toMatchObject({ selectValue: 360 });
    expect(resetTime).toEqual(expect.objectContaining({
      start: expect.any(String),
      end: expect.any(String),
    }));

    expect(getUnifiedFilterTimeSelectorDefaultValue(resetValues[TIME_ID])).toMatchObject({
      selectValue: 360,
      rangePickerVaule: null,
    });

    const request = buildWidgetRequestParams({
      config: {
        dataSourceParams: [
          { name: 'time', type: 'timeRange', value: 15, filterType: 'filter' },
        ],
      },
      unifiedFilterValues: resetValues,
      filterBindings: { [TIME_ID]: true },
      filterDefinitions: [definition],
    });
    expect(request).toEqual({ time: { selectValue: 360 } });
  });

  test('空时间默认值重置为 null，数字默认值保持原样', () => {
    expect(buildResetFilterValues([timeDefinition(null)])).toEqual({
      [TIME_ID]: null,
    });
    expect(buildResetFilterValues([{
      id: 'limit__number',
      key: 'limit',
      name: '条数',
      type: 'number',
      defaultValue: -1,
      order: 0,
      enabled: true,
    }])).toEqual({ limit__number: -1 });
  });
});

describe('取消编辑与保存后的时间当前值', () => {
  test('回滚后按已保存默认值重算时间当前值', () => {
    const rolledBack = [timeDefinition(legacyDefault)];
    const customized = normalizeTimeRangeFilterValue(15, REFERENCE);
    const next = recomputeTimeRangeValuesFromDefaults(rolledBack, {
      [TIME_ID]: customized,
      env__string: 'prod',
    });

    expect(next[TIME_ID]).toMatchObject({ selectValue: 360 });
    expect(next.env__string).toBe('prod');
  });

  test('保存时当前值仍停在旧默认上才换成新默认', () => {
    const previous = timeDefinition(legacyDefault);
    const next = timeDefinition(normalizeTimeRangeFilterValue(15, REFERENCE));
    const stillOnPrevious = normalizeTimeRangeFilterValue(360, '2026-10-08T00:00:00.000Z');
    const applied = applyChangedDefaultsIfStillOnPrevious(
      [previous],
      [next],
      { [TIME_ID]: stillOnPrevious },
    );
    expect(applied.updatedIds).toEqual([TIME_ID]);
    expect(applied.values[TIME_ID]).toMatchObject({ selectValue: 15 });

    const customized = normalizeTimeRangeFilterValue(60, REFERENCE);
    const kept = applyChangedDefaultsIfStillOnPrevious(
      [previous],
      [next],
      { [TIME_ID]: customized },
    );
    expect(kept.updatedIds).toEqual([]);
    expect(kept.values[TIME_ID]).toEqual(customized);
  });
});

describe('仪表盘加载不因资源回调身份变化重拉', () => {
  test('loadDashboardData 用请求序号丢弃过期响应，且 effect 不依赖不稳定回调', () => {
    const source = readFileSync(
      path.resolve(
        process.cwd(),
        'src/app/ops-analysis/(pages)/view/dashBoard/index.tsx',
      ),
      'utf8',
    );
    const effect = source.match(
      /const loadDashboardData = async \(\) => \{[\s\S]*?\}, \[[\s\S]*?\]\);/,
    );
    expect(effect?.[0]).toBeTruthy();
    expect(effect?.[0]).toContain('isCurrentLoad');
    expect(effect?.[0]).toContain('dashboardLoadSeqRef');
    expect(effect?.[0]).not.toContain('loadCanvasNamespaces,');
    expect(effect?.[0]).not.toContain('syncDashboardCanvasResources,');
    expect(source).toContain('recomputeTimeRangeValuesFromDefaults');
    expect(source).toContain('applyChangedDefaultsIfStillOnPrevious');
  });

  test('配置弹窗和筛选栏都走统一时间默认值', () => {
    const bar = readFileSync(
      path.resolve(
        process.cwd(),
        'src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx',
      ),
      'utf8',
    );
    const modal = readFileSync(
      path.resolve(
        process.cwd(),
        'src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx',
      ),
      'utf8',
    );
    expect(bar).toContain('getUnifiedFilterTimeSelectorDefaultValue');
    expect(modal).toContain('getUnifiedFilterTimeSelectorDefaultValue');
    expect(bar).not.toContain('!timeValue.start || !timeValue.end');
    expect(modal).not.toContain('!timeValue.start || !timeValue.end');
  });
});
