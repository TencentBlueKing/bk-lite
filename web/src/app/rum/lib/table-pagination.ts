'use client';

import { useEffect, useMemo, useState } from 'react';

export const RUM_PAGE_SIZES = [10, 20, 50, 100] as const;
export const RUM_DEFAULT_PAGE_SIZE = 20;

export function parseRumPageSize(raw: unknown): number {
  const n = Number(raw);
  return (RUM_PAGE_SIZES as readonly number[]).includes(n) ? n : RUM_DEFAULT_PAGE_SIZE;
}

export function sliceRumPage<T>(rows: readonly T[], page: number, pageSize: number) {
  const size = Math.max(1, Math.floor(Number(pageSize) || RUM_DEFAULT_PAGE_SIZE));
  const total = rows.length;
  const maxPage = Math.max(1, Math.ceil(total / size) || 1);
  const current = Math.min(Math.max(1, Number(page) || 1), maxPage);
  const start = (current - 1) * size;
  return { current, pageSize: size, total, rows: rows.slice(start, start + size) };
}

export function rumListPagination({
  current,
  pageSize,
  total,
  onChange,
}: {
  current: number;
  pageSize: number;
  total: number;
  onChange: (page: number, pageSize: number) => void;
}) {
  return {
    current,
    pageSize,
    total,
    showSizeChanger: true,
    onChange: (nextPage: number, nextSize?: number) => {
      const size = parseRumPageSize(nextSize);
      onChange(size !== pageSize ? 1 : nextPage, size);
    },
  };
}

export function useRumClientPager<T>(rows: readonly T[], resetKey: string) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(RUM_DEFAULT_PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [resetKey]);

  const sliced = useMemo(() => sliceRumPage(rows, page, pageSize), [rows, page, pageSize]);

  return {
    rows: sliced.rows,
    pagination: rumListPagination({
      current: sliced.current,
      pageSize: sliced.pageSize,
      total: sliced.total,
      onChange: (nextPage, nextSize) => {
        setPage(nextPage);
        setPageSize(nextSize);
      },
    }),
  };
}
