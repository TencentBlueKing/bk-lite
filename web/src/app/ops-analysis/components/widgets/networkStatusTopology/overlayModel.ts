import type {
  NetworkNodeStatus,
  NetworkStatusTopologyNode,
} from '@/app/ops-analysis/types/sceneWidget';

export const NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS = [
  'cmdb/get_monitor_ids_by_inst_uuids',
  'monitor/query_latest_active_alerts',
] as const;

const [CMDB_OVERLAY_REST_API, MONITOR_OVERLAY_REST_API] =
  NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS;

export interface OverlayDataSource {
  id: number;
  rest_api?: string;
  is_build_in?: boolean;
}

export interface OverlayNodeVisual {
  status: NetworkNodeStatus;
  pulse: boolean;
  color: NonNullable<NetworkStatusTopologyNode['color']>;
}

interface OverlaySourceNode {
  id: string;
  model_id: string;
  name: string;
  hop: number;
  [key: string]: unknown;
}

interface OverlayMapping {
  inst_uuid: string;
  model_id?: string;
  monitor_id: string;
}

interface OverlaySummary {
  instance_id: string;
  count: number;
  max_level: string | null;
}

const UNKNOWN_VISUAL: OverlayNodeVisual = {
  status: 'unknown',
  pulse: false,
  color: 'gray',
};

const pickUniqueRestApiId = (
  sources: OverlayDataSource[],
  restApi: string,
): number | undefined => {
  const matches = sources.filter((source) => source.rest_api === restApi);
  if (matches.length === 1) {
    return matches[0].id;
  }
  const builtins = matches.filter((source) => source.is_build_in);
  if (builtins.length === 1) {
    return builtins[0].id;
  }
  return undefined;
};

export function pickOverlayDataSourceIds(
  sources: OverlayDataSource[],
): { cmdbId?: number; monitorId?: number } {
  const cmdbId = pickUniqueRestApiId(sources, CMDB_OVERLAY_REST_API);
  const monitorId = pickUniqueRestApiId(sources, MONITOR_OVERLAY_REST_API);
  return {
    ...(cmdbId !== undefined ? { cmdbId } : {}),
    ...(monitorId !== undefined ? { monitorId } : {}),
  };
}

export function mapMonitorLevelToNodeStatus(
  level: string | null | undefined,
  count: number,
): OverlayNodeVisual {
  if (!count) {
    return { status: 'normal', pulse: false, color: 'green' };
  }
  const normalized = String(level || '').toLowerCase();
  if (normalized === 'critical') {
    return { status: 'critical', pulse: true, color: 'red' };
  }
  if (normalized === 'error') {
    return { status: 'error', pulse: false, color: 'red' };
  }
  return { status: 'warning', pulse: false, color: 'yellow' };
}

const resolveMonitorId = (monitorId: string | undefined) =>
  typeof monitorId === 'string' ? monitorId.trim() : '';

export function applyMonitorOverlay(input: {
  nodes: OverlaySourceNode[];
  mappings: OverlayMapping[];
  summaries: OverlaySummary[];
}): NetworkStatusTopologyNode[] {
  const mappingByUuid = new Map(
    input.mappings.map((mapping) => [mapping.inst_uuid, mapping]),
  );
  const summaryByInstance = new Map(
    input.summaries.map((summary) => [summary.instance_id, summary]),
  );

  return input.nodes.map((node) => {
    const mapping = mappingByUuid.get(node.id);
    const monitorId = resolveMonitorId(mapping?.monitor_id);
    if (!mapping || !monitorId) {
      return {
        ...node,
        ...UNKNOWN_VISUAL,
        alert_count: 0,
      } as NetworkStatusTopologyNode;
    }

    const summary = summaryByInstance.get(monitorId);
    if (!summary) {
      return {
        ...node,
        monitor_id: monitorId,
        ...UNKNOWN_VISUAL,
        alert_count: 0,
      } as NetworkStatusTopologyNode;
    }

    return {
      ...node,
      monitor_id: monitorId,
      alert_count: summary.count,
      ...mapMonitorLevelToNodeStatus(summary.max_level, summary.count),
    } as NetworkStatusTopologyNode;
  });
}

export function canOpenAlertModal(
  node: Pick<NetworkStatusTopologyNode, 'status' | 'alert_count'>,
): boolean {
  return node.status !== 'unknown' && Number(node.alert_count || 0) > 0;
}
