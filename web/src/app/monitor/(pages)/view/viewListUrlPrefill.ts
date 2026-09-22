import { displayFieldKey } from './instanceViewColumns';

export const isUrlColonyObject = (name?: string | null): boolean =>
  name === 'Process' || name === 'Pod' || name === 'Node';

export const isUrlSortObject = (name?: string | null): boolean =>
  isUrlColonyObject(name) && name !== 'Process';

export const readUrlColonyIds = (
  searchParams: Pick<URLSearchParams, 'get'>,
  objectName?: string | null
): string[] => {
  if (!isUrlColonyObject(objectName)) return [];
  const raw = String(searchParams.get('vm_params.instance_id') || '').trim();
  return raw ? [raw] : [];
};

/**
 * Process / Pod / Node keep URL colony ids even when the VM enum is missing them.
 * Other objects wipe leftover colony so Host/K3SPod do not inherit instance_id.
 */
export const resolveColonyAfterEnumLoad = (
  objectName: string | null | undefined,
  colony: string[]
): string[] => (isUrlColonyObject(objectName) ? colony : []);

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
