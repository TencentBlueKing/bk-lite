export const GENERIC_STRUCTURES = ['table', 'value', 'category', 'series'] as const;

export type GenericStructure = (typeof GENERIC_STRUCTURES)[number];

export const chartRequiredStructure = (chartType?: string): GenericStructure | null => {
  switch (chartType) {
    case 'table':
    case 'eventTable':
      return 'table';
    case 'single':
      return 'value';
    case 'bar':
    case 'pie':
    case 'topN':
      return 'category';
    case 'line':
      return 'series';
    default:
      return null;
  }
};

export const readGenericStructure = (raw: unknown): GenericStructure | null => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const structure = (raw as { structure?: unknown }).structure;
  if (typeof structure !== 'string') return null;
  return (GENERIC_STRUCTURES as readonly string[]).includes(structure)
    ? structure as GenericStructure
    : null;
};

export const genericStructureMismatch = (
  raw: unknown,
  chartType?: string,
): { current: GenericStructure; required: GenericStructure } | null => {
  const required = chartRequiredStructure(chartType);
  const current = readGenericStructure(raw);
  if (!required || !current || required === current) return null;
  return { current, required };
};

/** 分页后的分类结果画成饼图时，占比只覆盖当前页。 */
export const piePageShare = (
  raw: unknown,
): { page: number; pageSize: number; count: number } | null => {
  if (readGenericStructure(raw) !== 'category') return null;
  const data = raw as {
    page?: unknown;
    page_size?: unknown;
    count?: unknown;
    items?: unknown;
  };
  const page = Number(data.page);
  const pageSize = Number(data.page_size);
  const count = Number(data.count);
  const shown = Array.isArray(data.items) ? data.items.length : 0;
  if (!Number.isInteger(page) || !Number.isInteger(pageSize) || !Number.isInteger(count)) {
    return null;
  }
  if (page < 1 || pageSize < 1 || count < 0) return null;
  if (page === 1 && count <= shown) return null;
  return { page, pageSize, count };
};
