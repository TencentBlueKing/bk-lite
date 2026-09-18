import type { ListItem } from '@/app/cmdb/types/assetManage';

const ASSOCIATION_PICKER_RANK: Record<string, number> = {
  run: 0,
  connect: 1,
};

function asstIdOf(item: ListItem): string {
  return typeof item.asst_id === 'string' ? item.asst_id : '';
}

export function sortAssociationPickerOptions(items: readonly ListItem[]): ListItem[] {
  return [...items].sort((left, right) => {
    const byType =
      (ASSOCIATION_PICKER_RANK[asstIdOf(left)] ?? 2) -
      (ASSOCIATION_PICKER_RANK[asstIdOf(right)] ?? 2);
    if (byType !== 0) return byType;
    return String(left.name || '').localeCompare(String(right.name || ''), 'zh');
  });
}
