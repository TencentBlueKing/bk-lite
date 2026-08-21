import type { NetworkStatusTopologyLink, NetworkStatusTopologyNode } from '@/app/ops-analysis/types/sceneWidget';
import { formatUnit } from '@/app/ops-analysis/utils/unitFormat';
import {
  getColorByThreshold,
  type ThresholdColorConfig,
} from '@/app/ops-analysis/utils/thresholdUtils';

export type LinkTrafficDisplay = 'inbound' | 'outbound';

export type InterfaceOperKind = 'up' | 'down' | 'unknown';

export type LinkConnectStatus = 'up' | 'down' | 'unknown';

export type PortMatchReason =
  | 'ok'
  | 'unmonitored'
  | 'unmatched'
  | 'query_failed';

export interface InterfaceMetricItem {
  instance_id: string;
  ifDescr: string;
  metrics: Record<string, number>;
}

export interface PortRuntime {
  portName: string;
  matchReason: PortMatchReason;
  ifDescr?: string;
  operKind: InterfaceOperKind;
  inbound?: number;
  outbound?: number;
  bandwidthMbps?: number;
  bandwidthBps?: number;
  inErrors?: number;
  outErrors?: number;
  inDiscards?: number;
  outDiscards?: number;
}

export interface LinkRuntime {
  status: LinkConnectStatus;
  source: PortRuntime;
  target: PortRuntime;
}

const TRAFFIC_DISPLAYS: LinkTrafficDisplay[] = ['inbound', 'outbound'];

const NAME_REPLACEMENTS: Array<[string, string]> = [
  ['gigabitethernet', 'gi'],
  ['tengigabitethernet', 'te'],
  ['ten-gigabitethernet', 'te'],
  ['ethernet', 'eth'],
  ['port-channel', 'po'],
];

export const normalizeLinkTrafficDisplays = (
  value: ReadonlyArray<string> | undefined,
): LinkTrafficDisplay[] => {
  if (value == null) return [...TRAFFIC_DISPLAYS];
  const seen = new Set<LinkTrafficDisplay>();
  value.forEach((item) => {
    if (item === 'inbound' || item === 'outbound') seen.add(item);
  });
  return TRAFFIC_DISPLAYS.filter((item) => seen.has(item));
};

export const normalizeInterfaceName = (value: string): string =>
  String(value || '').trim().toLowerCase().split(/\s+/).join('');

export const buildInterfaceNameCandidates = (value: string): Set<string> => {
  const normalized = normalizeInterfaceName(value);
  if (!normalized) return new Set();
  const candidates = new Set<string>([normalized]);
  NAME_REPLACEMENTS.forEach(([full, short]) => {
    if (normalized.startsWith(full)) {
      candidates.add(`${short}${normalized.slice(full.length)}`);
    }
    if (normalized.startsWith(short)) {
      candidates.add(`${full}${normalized.slice(short.length)}`);
    }
  });
  return candidates;
};

export const matchIfDescr = (
  portName: string,
  ifDescrs: ReadonlyArray<string>,
): string | undefined => {
  const portCandidates = buildInterfaceNameCandidates(portName);
  if (portCandidates.size === 0) return undefined;
  return ifDescrs.find((item) => {
    const descrCandidates = buildInterfaceNameCandidates(item);
    for (const candidate of portCandidates) {
      if (descrCandidates.has(candidate)) return true;
    }
    return false;
  });
};

export const mapOperStatus = (value: number | undefined): InterfaceOperKind => {
  if (value === 1) return 'up';
  if (value === 2 || value === 7) return 'down';
  return 'unknown';
};

export const pickTrafficValue = (
  metrics: Record<string, number> | undefined,
  direction: 'in' | 'out',
): number | undefined => {
  if (!metrics) return undefined;
  const hc = direction === 'in'
    ? metrics.interface_ifHCInOctets
    : metrics.interface_ifHCOutOctets;
  if (Number.isFinite(hc)) return hc;
  const legacy = direction === 'in'
    ? metrics.interface_ifInOctets
    : metrics.interface_ifOutOctets;
  return Number.isFinite(legacy) ? legacy : undefined;
};

export const pickBandwidth = (
  metrics: Record<string, number> | undefined,
): { mbps?: number; bps?: number } => {
  if (!metrics) return {};
  if (Number.isFinite(metrics.interface_ifHighSpeed)) {
    return { mbps: metrics.interface_ifHighSpeed };
  }
  if (Number.isFinite(metrics.interface_ifSpeed)) {
    return { bps: metrics.interface_ifSpeed };
  }
  return {};
};

export const formatByteRate = (value: number | undefined): string => {
  if (!Number.isFinite(value)) return '';
  const formatted = formatUnit(Number(value), 'bytesIEC');
  return `${formatted.value} ${formatted.suffix}/s`;
};

export const formatBandwidth = (port: Pick<PortRuntime, 'bandwidthMbps' | 'bandwidthBps'>): string => {
  if (Number.isFinite(port.bandwidthMbps)) {
    const mbps = Number(port.bandwidthMbps);
    if (mbps >= 1000) {
      const gbps = mbps / 1000;
      const text = Number.isInteger(gbps) ? String(gbps) : gbps.toFixed(1);
      return `${text} Gbps`;
    }
    const text = Number.isInteger(mbps) ? String(mbps) : mbps.toFixed(1);
    return `${text} Mbps`;
  }
  if (Number.isFinite(port.bandwidthBps)) {
    return formatUnit(Number(port.bandwidthBps), 'bps').text;
  }
  return '';
};

export const formatPacketRate = (value: number | undefined): string => {
  if (!Number.isFinite(value)) return '';
  return `${formatUnit(Number(value), 'short').text}/s`;
};

export interface PortTrafficLine {
  text: string;
  fill?: string;
}

export const resolveTrafficLineFill = (
  value: number | undefined,
  thresholds: ReadonlyArray<ThresholdColorConfig> | undefined,
  defaultFill: string,
): string => {
  if (!thresholds?.length || !Number.isFinite(value)) return defaultFill;
  return getColorByThreshold(Number(value), [...thresholds], defaultFill);
};

export const buildPortTrafficLines = (
  port: PortRuntime,
  displays: ReadonlyArray<LinkTrafficDisplay>,
  options?: {
    inboundThresholds?: ReadonlyArray<ThresholdColorConfig>;
    outboundThresholds?: ReadonlyArray<ThresholdColorConfig>;
    defaultFill?: string;
  },
): PortTrafficLine[] => {
  if (port.matchReason !== 'ok') return [];
  const defaultFill = options?.defaultFill || '';
  const lines: PortTrafficLine[] = [];
  if (displays.includes('inbound')) {
    const text = formatByteRate(port.inbound);
    if (text) {
      lines.push({
        text: `↓ ${text}`,
        fill: resolveTrafficLineFill(
          port.inbound,
          options?.inboundThresholds,
          defaultFill,
        ),
      });
    }
  }
  if (displays.includes('outbound')) {
    const text = formatByteRate(port.outbound);
    if (text) {
      lines.push({
        text: `↑ ${text}`,
        fill: resolveTrafficLineFill(
          port.outbound,
          options?.outboundThresholds,
          defaultFill,
        ),
      });
    }
  }
  return lines;
};

export const resolveLinkConnectStatus = (
  sourceKind: InterfaceOperKind,
  targetKind: InterfaceOperKind,
): LinkConnectStatus => {
  if (sourceKind === 'down' || targetKind === 'down') return 'down';
  if (sourceKind === 'up' && targetKind === 'up') return 'up';
  return 'unknown';
};

const indexInterfaceItems = (items: ReadonlyArray<InterfaceMetricItem>) => {
  const byInstance = new Map<string, Map<string, InterfaceMetricItem>>();
  items.forEach((item) => {
    const instanceId = String(item.instance_id || '');
    const ifDescr = String(item.ifDescr || '');
    if (!instanceId || !ifDescr) return;
    const bucket = byInstance.get(instanceId) ?? new Map();
    bucket.set(ifDescr, item);
    byInstance.set(instanceId, bucket);
  });
  return byInstance;
};

const buildPortRuntime = (
  portName: string,
  monitorId: string | undefined,
  itemsByDescr: Map<string, InterfaceMetricItem> | undefined,
  queryFailed: boolean,
): PortRuntime => {
  const name = String(portName || '').trim();
  if (!monitorId) {
    return {
      portName: name,
      matchReason: 'unmonitored',
      operKind: 'unknown',
    };
  }
  if (queryFailed) {
    return {
      portName: name,
      matchReason: 'query_failed',
      operKind: 'unknown',
    };
  }
  const matched = matchIfDescr(name, Array.from(itemsByDescr?.keys() || []));
  if (!matched) {
    return {
      portName: name,
      matchReason: 'unmatched',
      operKind: 'unknown',
    };
  }
  const metrics = itemsByDescr?.get(matched)?.metrics;
  const bandwidth = pickBandwidth(metrics);
  return {
    portName: name,
    matchReason: 'ok',
    ifDescr: matched,
    operKind: mapOperStatus(metrics?.interface_ifOperStatus),
    inbound: pickTrafficValue(metrics, 'in'),
    outbound: pickTrafficValue(metrics, 'out'),
    bandwidthMbps: bandwidth.mbps,
    bandwidthBps: bandwidth.bps,
    inErrors: Number.isFinite(metrics?.interface_ifInErrors)
      ? metrics?.interface_ifInErrors
      : undefined,
    outErrors: Number.isFinite(metrics?.interface_ifOutErrors)
      ? metrics?.interface_ifOutErrors
      : undefined,
    inDiscards: Number.isFinite(metrics?.interface_ifInDiscards)
      ? metrics?.interface_ifInDiscards
      : undefined,
    outDiscards: Number.isFinite(metrics?.interface_ifOutDiscards)
      ? metrics?.interface_ifOutDiscards
      : undefined,
  };
};

export const applyLinkRuntime = (input: {
  links: NetworkStatusTopologyLink[];
  nodes: NetworkStatusTopologyNode[];
  items: InterfaceMetricItem[];
  queryFailed?: boolean;
}): Array<NetworkStatusTopologyLink & { runtime: LinkRuntime }> => {
  const monitorByNode = new Map(
    input.nodes.map((node) => [String(node.id), String(node.monitor_id || '').trim()]),
  );
  const itemsByInstance = indexInterfaceItems(input.items);
  const queryFailed = Boolean(input.queryFailed);

  return input.links.map((link) => {
    const sourceId = String(link.source || link.source_device || '');
    const targetId = String(link.target || link.target_device || '');
    const sourceMonitor = monitorByNode.get(sourceId) || undefined;
    const targetMonitor = monitorByNode.get(targetId) || undefined;
    const source = buildPortRuntime(
      String(link.sourcePort || link.source_port || link.source_inst_name || ''),
      sourceMonitor,
      sourceMonitor ? itemsByInstance.get(sourceMonitor) : undefined,
      queryFailed,
    );
    const target = buildPortRuntime(
      String(link.targetPort || link.target_port || link.target_inst_name || ''),
      targetMonitor,
      targetMonitor ? itemsByInstance.get(targetMonitor) : undefined,
      queryFailed,
    );
    return {
      ...link,
      runtime: {
        status: resolveLinkConnectStatus(source.operKind, target.operKind),
        source,
        target,
      },
    };
  });
};
