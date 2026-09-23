import type { ObjectItem } from '@/app/monitor/types';

const PROBE_OBJECT_NAMES = new Set(['Website', 'Ping', 'TCPPort']);
const PROBE_SEARCH_FACTS = new Set(['collector.nodes', 'probe.target']);

export const getAssetSearchPlaceholderKey = (
  object?: Pick<ObjectItem, 'name' | 'instance_summary_columns'> | null
) => {
  if (object?.name === 'Process') {
    return 'monitor.views.searchPlaceholderProcess';
  }
  const facts = (object?.instance_summary_columns || []).map((column) => column.fact);
  if (
    PROBE_OBJECT_NAMES.has(object?.name || '') ||
    facts.some((fact) => PROBE_SEARCH_FACTS.has(fact))
  ) {
    return 'monitor.views.searchPlaceholderProbe';
  }
  return 'monitor.views.searchPlaceholderDefault';
};
