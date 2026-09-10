// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { useOpsAnalysisQueryState } from '@/app/ops-analysis/hooks/useOpsAnalysisQueryState';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';

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
