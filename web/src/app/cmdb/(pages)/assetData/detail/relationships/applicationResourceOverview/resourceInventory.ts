import type { ApplicationResourceInstanceGroup } from '@/app/cmdb/types/applicationResourceOverview';

const normalizeQuery = (query: string) => query.trim().toLowerCase();

export function filterResourceGroups(
  groups: ApplicationResourceInstanceGroup[],
  query: string
): ApplicationResourceInstanceGroup[] {
  const needle = normalizeQuery(query);
  if (!needle) return groups;

  return groups.flatMap((group) => {
    const keys = group.column_defs.map((column) => column.key);
    const items = group.items.filter((item) =>
      keys.some((key) => String(item[key] ?? '').toLowerCase().includes(needle))
    );
    if (!items.length) return [];
    return [{
      ...group,
      items,
      count: items.length,
    }];
  });
}
