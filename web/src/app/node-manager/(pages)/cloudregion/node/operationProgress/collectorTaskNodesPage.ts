export interface CollectorTaskNodesPageInput {
  current: number;
  pageSize: number;
}

export interface CollectorTaskNodesPageQuery {
  page?: number;
  page_size?: number;
}

export interface CollectorTaskNodesPageResponse<T = unknown> {
  items?: T[] | null;
  count?: number;
}

export interface CollectorTaskNodesPageResult<T = unknown> {
  items: T[];
  total: number;
}

const DEFAULT_PAGE = 1;
const DEFAULT_PAGE_SIZE = 20;
const MAX_PAGE_SIZE = 500;

export function buildCollectorTaskNodesPageQuery(
  input: CollectorTaskNodesPageInput
): CollectorTaskNodesPageQuery {
  const page = Number.isFinite(input.current)
    ? Math.max(DEFAULT_PAGE, Math.trunc(input.current))
    : DEFAULT_PAGE;
  const rawPageSize = Number.isFinite(input.pageSize)
    ? Math.trunc(input.pageSize)
    : DEFAULT_PAGE_SIZE;
  const pageSize = Math.min(
    MAX_PAGE_SIZE,
    Math.max(1, rawPageSize || DEFAULT_PAGE_SIZE)
  );
  return {
    page,
    page_size: pageSize
  };
}

export function resolveCollectorTaskNodesPage<T = unknown>(
  response: CollectorTaskNodesPageResponse<T> | null | undefined
): CollectorTaskNodesPageResult<T> {
  const items = Array.isArray(response?.items) ? response.items : [];
  const total =
    typeof response?.count === 'number' && Number.isFinite(response.count)
      ? response.count
      : items.length;
  return {
    items,
    total
  };
}
