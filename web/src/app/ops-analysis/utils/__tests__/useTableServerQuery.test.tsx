import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useTableServerQuery } from '@/app/ops-analysis/utils/useTableServerQuery';

const sourceParams = [{ name: 'page' }, { name: 'page_size' }];

const pageOf = (count: number, page: number, pageSize: number) => ({
  items: Array.from({ length: Math.min(pageSize, count) }, (_, index) => ({ id: index })),
  count,
  page,
  page_size: pageSize,
});

describe('useTableServerQuery', () => {
  it('hides the self-paged hint until the new payload arrives', () => {
    const previous = pageOf(1200, 3, 5);
    const saved = [
      { name: 'page', value: 3 },
      { name: 'page_size', value: 5 },
    ];
    const { result, rerender } = renderHook(
      (props: { rawData: unknown; savedParams: Array<{ name: string; value?: number }> }) => useTableServerQuery({
        rawData: props.rawData,
        sourceParams,
        savedParams: props.savedParams,
        onQueryChange: vi.fn(),
      }),
      { initialProps: { rawData: previous, savedParams: saved } },
    );

    expect(result.current.selfPaged).toBe(false);
    expect(result.current.isPaginated).toBe(true);

    rerender({ rawData: previous, savedParams: [] });

    expect(result.current.selfPaged).toBe(false);
    expect(result.current.isPaginated).toBe(false);
    expect(result.current.rows).toHaveLength(5);

    rerender({ rawData: pageOf(1200, 1, 20), savedParams: [] });

    expect(result.current.selfPaged).toBe(true);
    expect(result.current.isPaginated).toBe(true);
    expect(result.current.pagination).toEqual({ current: 1, pageSize: 20, total: 1200 });
  });

  it('keeps the pager while a requested page is still loading', () => {
    const loaded = pageOf(1200, 1, 20);
    const { result } = renderHook(() => useTableServerQuery({
      rawData: loaded,
      sourceParams,
      savedParams: [],
      onQueryChange: vi.fn(),
    }));

    expect(result.current.selfPaged).toBe(true);

    act(() => {
      result.current.handleTableChange({ current: 2, pageSize: 20 });
    });

    expect(result.current.selfPaged).toBe(false);
    expect(result.current.isPaginated).toBe(true);
    expect(result.current.pagination.current).toBe(2);
    expect(result.current.pagination.pageSize).toBe(20);
  });
});
