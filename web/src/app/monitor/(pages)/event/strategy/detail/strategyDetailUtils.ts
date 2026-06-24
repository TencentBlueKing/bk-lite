import { SegmentedItem } from '@/app/monitor/types';

export const resolveInitialMetricPluginId = ({
  type,
  pluginList,
  policyCollectType,
}: {
  type: string;
  pluginList: SegmentedItem[];
  policyCollectType?: string | number | null;
}): string | number | undefined => {
  if (!pluginList.length) return undefined;
  if (!['add', 'builtIn'].includes(type) && policyCollectType) {
    const matched = pluginList.find(
      (item) => String(item.value) === String(policyCollectType)
    );
    if (matched) return matched.value;
  }
  return pluginList[0]?.value;
};
