// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { useOpsAnalysisQueryState } from '@/app/ops-analysis/hooks/useOpsAnalysisQueryState';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import { buildRelativeTimeRangeFilterValue } from '@/app/ops-analysis/utils/filterValue';

const ORGANIZATION_FILTER: UnifiedFilterDefinition = {
  id: 'organization__string',
  key: 'organization',
  name: '组织',
  type: 'string',
  inputMode: 'organization',
  order: 0,
  enabled: true,
};

describe('useOpsAnalysisQueryState applyQuery organization seed', () => {
  test('分享态搜索时把清空的组织筛填回 space_id', () => {
    const { result } = renderHook(() => useOpsAnalysisQueryState());

    act(() => {
      result.current.resetQueryState({
        definitions: [ORGANIZATION_FILTER],
        organizationId: 8,
      });
    });
    expect(result.current.filterValues.organization__string).toBe('8');

    act(() => {
      result.current.applyQuery({ organization__string: '' }, undefined);
    });
    expect(result.current.filterValues.organization__string).toBe('8');
    expect(result.current.appliedFilterValues.organization__string).toBe('8');
  });

  test('非分享态搜索不回填组织', () => {
    const { result } = renderHook(() => useOpsAnalysisQueryState());

    act(() => {
      result.current.resetQueryState({
        definitions: [ORGANIZATION_FILTER],
      });
    });

    act(() => {
      result.current.applyQuery({ organization__string: '' }, undefined);
    });
    expect(result.current.filterValues.organization__string).toBe('');
  });
});

describe('useOpsAnalysisQueryState applyFilterConfigConfirm defaults', () => {
  test('确认全局筛选时，仍停在旧相对默认的 time 改用新默认', () => {
    const { result } = renderHook(() => useOpsAnalysisQueryState());
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
    const previous: UnifiedFilterDefinition = {
      id: 'time__timeRange',
      key: 'time',
      name: '时间范围',
      type: 'timeRange',
      defaultValue: previousDefault,
      order: 0,
      enabled: true,
    };

    act(() => {
      result.current.resetQueryState({
        definitions: [previous],
        filterValues: { 'time__timeRange': runtimeValue },
        appliedFilterValues: { 'time__timeRange': runtimeValue },
      });
    });

    act(() => {
      result.current.applyFilterConfigConfirm([
        { ...previous, defaultValue: nextDefault },
      ]);
    });

    expect(result.current.filterValues['time__timeRange']).toMatchObject({
      selectValue: 15,
    });
    expect(result.current.appliedFilterValues['time__timeRange']).toMatchObject({
      selectValue: 15,
    });
  });
});
