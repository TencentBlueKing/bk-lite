import { describe, expect, test } from 'vitest';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import {
  applySelectedOrganizationToFilterValues,
  fillMissingOrganizationFilterValues,
  isOrganizationFilterDefinition,
} from '@/app/ops-analysis/utils/unifiedFilterState';

const ORGANIZATION_FILTER: UnifiedFilterDefinition = {
  id: 'organization__string',
  key: 'organization',
  name: '组织',
  type: 'string',
  inputMode: 'organization',
  order: 0,
  enabled: true,
};

const TIME_FILTER: UnifiedFilterDefinition = {
  id: 'time__timeRange',
  key: 'time',
  name: '时间',
  type: 'timeRange',
  order: 1,
  enabled: true,
  defaultValue: { selectValue: 10080 },
};

describe('applySelectedOrganizationToFilterValues', () => {
  test('识别组织树筛选定义', () => {
    expect(isOrganizationFilterDefinition(ORGANIZATION_FILTER)).toBe(true);
    expect(isOrganizationFilterDefinition(TIME_FILTER)).toBe(false);
  });

  test('用当前工作组织填入空的组织筛选，不改时间筛选', () => {
    const next = fillMissingOrganizationFilterValues(
      [ORGANIZATION_FILTER, TIME_FILTER],
      { 'time__timeRange': { selectValue: 10080 } },
      12,
    );
    expect(next.organization__string).toBe('12');
    expect(next['time__timeRange']).toEqual({ selectValue: 10080 });
  });

  test('打开盘或查询时保留画布已选组织', () => {
    const current = { organization__string: '3', 'time__timeRange': { selectValue: 10080 } };
    const next = fillMissingOrganizationFilterValues(
      [ORGANIZATION_FILTER, TIME_FILTER],
      current,
      12,
    );
    expect(next).toBe(current);
  });

  test('当前工作组织变化时覆盖盘上已选组织', () => {
    const next = applySelectedOrganizationToFilterValues(
      [ORGANIZATION_FILTER],
      { organization__string: '3' },
      9,
    );
    expect(next.organization__string).toBe('9');
  });

  test('没有当前工作组织时保持原值', () => {
    const current = { organization__string: '3' };
    expect(
      applySelectedOrganizationToFilterValues([ORGANIZATION_FILTER], current, null),
    ).toBe(current);
  });
});
