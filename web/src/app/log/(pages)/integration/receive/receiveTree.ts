import { TreeItem } from '@/app/log/types';

export interface ReceiveCollectType {
  id: string | number;
  name: string;
  display_name?: string;
  display_category?: string;
  instance_count?: number;
}

const PASSIVE_COLLECT_TYPES = new Set(['syslog', 'snmp_trap']);

export function buildReceiveTree(
  data: ReceiveCollectType[],
  categoryEnum: { id: string; name: string }[],
  allTitle: string
): TreeItem[] {
  const categoryMap = categoryEnum.reduce(
    (acc: Record<string, string>, item) => {
      acc[item.id] = item.name;
      return acc;
    },
    {}
  );
  const groupedData = data.reduce(
    (acc, item) => {
      if (PASSIVE_COLLECT_TYPES.has(item.name)) return acc;
      const category = item.display_category || 'other';
      if (!acc[category]) {
        acc[category] = {
          title: categoryMap[category] || category,
          key: category,
          children: []
        };
      }
      acc[category].children.push({
        title: `${item.display_name || item.name}(${Number(item.instance_count || 0)})`,
        label: item.display_name || item.name || '--',
        key: String(item.id),
        children: []
      });
      return acc;
    },
    {} as Record<string, TreeItem>
  );

  const orderedTree = categoryEnum
    .filter((cat) => groupedData[cat.id])
    .map((cat) => groupedData[cat.id]);

  return [
    {
      title: allTitle,
      key: 'all',
      children: []
    },
    ...orderedTree
  ];
}
