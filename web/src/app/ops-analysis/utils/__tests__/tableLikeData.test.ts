import { describe, expect, it } from 'vitest';

import { parseTableLikeData } from '@/app/ops-analysis/utils/tableLikeData';

describe('parseTableLikeData', () => {
  it('uses count first and falls back to total for server pagination', () => {
    const items = [{ id: 1 }, { id: 2 }];

    expect(parseTableLikeData(
      { items, count: 80, total: 5 },
      { current: 1, pageSize: 20 },
      true,
    ).pagination.total).toBe(80);

    const bill = parseTableLikeData(
      { items, total: 80, page: 1, page_size: 20 },
      { current: 1, pageSize: 20 },
      true,
    );
    expect(bill.isPaginated).toBe(true);
    expect(bill.selfPaged).toBe(false);
    expect(bill.pagination).toEqual({ current: 1, pageSize: 20, total: 80 });
    expect(bill.rows).toHaveLength(2);
  });

  it('shows the echoed page when the request omitted paging and the payload is partial', () => {
    const parsed = parseTableLikeData(
      { items: [{ id: 1 }], count: 40, page: 1, page_size: 20 },
      {},
      true,
    );
    expect(parsed.selfPaged).toBe(true);
    expect(parsed.isPaginated).toBe(true);
    expect(parsed.pagination).toEqual({ current: 1, pageSize: 20, total: 40 });
  });

  it('keeps a complete echoed page unpaged', () => {
    const parsed = parseTableLikeData(
      { items: [{ id: 1 }], count: 1, page: 1, page_size: 20 },
      {},
      true,
    );
    expect(parsed.selfPaged).toBe(false);
    expect(parsed.isPaginated).toBe(false);
  });

  it('does not invent a pager when the payload has no page fields', () => {
    const parsed = parseTableLikeData(
      { items: [{ id: 1 }], count: 40 },
      {},
      true,
    );
    expect(parsed.isPaginated).toBe(false);
    expect(parsed.selfPaged).toBe(false);
  });
});