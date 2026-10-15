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
    expect(bill.pagination).toEqual({ current: 1, pageSize: 20, total: 80 });
    expect(bill.rows).toHaveLength(2);
  });
});