import { displayFieldKey } from './instanceViewColumns';

export const isUrlColonyObject = (name?: string | null): boolean =>
  name === 'Process' || name === 'Pod' || name === 'Node';

export const readUrlColonyIds = (
  searchParams: Pick<URLSearchParams, 'get'>,
  objectName?: string | null
): string[] => {
  if (!isUrlColonyObject(objectName)) return [];
  const raw = String(searchParams.get('vm_params.instance_id') || '').trim();
  return raw ? [raw] : [];
};

export const keepValidColonyIds = (
  colony: string[],
  options: Array<{ id?: string | number }>
): string[] => {
  if (!colony.length || !options.length) return colony;
  const valid = new Set(
    options.map((item) => String(item.id ?? '')).filter(Boolean)
  );
  return colony.filter((id) => valid.has(id));
};

interface DisplayFieldLike {
  column_key?: string;
  metrics?: Array<{ plugin?: string; metric?: string }>;
}

export const readUrlTableSort = (
  searchParams: Pick<URLSearchParams, 'get'>,
  displayFields?: DisplayFieldLike[] | null
): { key: string; order: 'ascend' | 'descend' } | null => {
  const ordering = String(searchParams.get('ordering') || '').trim();
  if (!ordering) return null;
  const rawOrder = String(searchParams.get('order') || 'desc')
    .trim()
    .toLowerCase();
  const order: 'ascend' | 'descend' =
    rawOrder === 'asc' ? 'ascend' : 'descend';
  if (ordering === 'time') {
    return { key: 'time', order };
  }
  const matched = (displayFields || []).find((col) => {
    if (col.column_key && col.column_key === ordering) return true;
    const binding = col.metrics?.[0];
    if (!binding) return false;
    return displayFieldKey(binding.plugin, binding.metric) === ordering;
  });
  return { key: matched?.column_key || ordering, order };
};
