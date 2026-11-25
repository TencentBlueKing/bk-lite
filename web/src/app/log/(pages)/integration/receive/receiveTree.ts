import { TreeItem } from '@/app/log/types';

export interface ReceiveCollectType {
  id: string | number;
  name: string;
  display_name?: string;
  display_category?: string;
  instance_count?: number;
}

const HIDDEN_RECEIVE_TYPES = new Set(['snmp_trap']);

export function buildReceiveTree(
  data: ReceiveCollectType[],
  categoryEnum: { id: string; name: string }[],
  options: {
    allTitle: string;
    sourceDeviceCount: number;
    sourceNodeTitle: (name: string) => string;
  }
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
      if (HIDDEN_RECEIVE_TYPES.has(item.name)) return acc;
      const category = item.display_category || 'other';
      if (!acc[category]) {
        acc[category] = {
          title: categoryMap[category] || category,
          key: category,
          children: []
        };
      }
      if (item.name === 'syslog') {
        const title = options.sourceNodeTitle(item.display_name || item.name);
        acc[category].children.push({
          title: `${title}(${options.sourceDeviceCount})`,
          label: title,
          key: String(item.id),
          children: []
        });
        return acc;
      }
      const count = Number(item.instance_count || 0);
      acc[category].children.push({
        title: `${item.display_name || item.name}(${count})`,
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
      title: options.allTitle,
      key: 'all',
      children: []
    },
    ...orderedTree
  ];
}
