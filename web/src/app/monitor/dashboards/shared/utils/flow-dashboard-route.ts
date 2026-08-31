import { getProfessionalDashboardUrl } from '../../metadata';
import type { FlowProtocol } from '../../objects/flow-common/constants';

export interface FlowDashboardPlugin {
  collect_type?: string;
  name?: string;
}

const FLOW_COLLECT_TYPES = new Set<FlowProtocol>(['netflow', 'sflow']);

export const isFlowCollectType = (collectType?: string | null): collectType is FlowProtocol =>
  FLOW_COLLECT_TYPES.has(String(collectType || '').trim() as FlowProtocol);

export const getFlowDashboardUrl = (collectType: FlowProtocol, queryString?: string) =>
  `/monitor/view/dashboard/${collectType}${queryString ? `?${queryString}` : ''}`;

export const resolveFlowCollectType = (
  plugins?: FlowDashboardPlugin[] | null,
  preferredCollectType?: string | null,
): FlowProtocol | null => {
  const preferred = String(preferredCollectType || '').trim();
  if (isFlowCollectType(preferred)) {
    return preferred;
  }

  const flowTypes = (plugins || [])
    .map((plugin) => String(plugin.collect_type || '').trim())
    .filter(isFlowCollectType);

  if (!flowTypes.length) return null;

  const unique = Array.from(new Set(flowTypes));
  if (unique.length === 1) return unique[0];
  if (unique.includes('netflow')) return 'netflow';
  return unique[0];
};

export const resolveDashboardUrl = (options: {
  monitorObjectName?: string | null;
  monitorObjectDisplayName?: string | null;
  instancePlugins?: FlowDashboardPlugin[] | null;
  preferredCollectType?: string | null;
  queryString?: string;
}) => {
  const queryString = options.queryString || '';
  const flowType = resolveFlowCollectType(options.instancePlugins, options.preferredCollectType);

  if (flowType) {
    return getFlowDashboardUrl(flowType, queryString);
  }

  return (
    getProfessionalDashboardUrl(
      options.monitorObjectName,
      options.monitorObjectDisplayName,
      queryString,
    ) || ''
  );
};
