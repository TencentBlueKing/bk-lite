/**
 * 把密集的运行态回写合并成一次状态更新，避免每个节点/连线一次 setState。
 */

import type {
  NetworkLinkRuntime,
  NetworkMetricRuntime,
  NetworkNodeRuntime,
} from '@/app/ops-analysis/types/networkTopology';

export const NETWORK_TOPOLOGY_RUNTIME_FLUSH_MS = 80;

export type NetworkInterfaceSummary = NonNullable<NetworkNodeRuntime['interface_summary']>;

export interface NetworkTopologyRuntimePending {
  metrics: Record<string, NetworkMetricRuntime[]>;
  links: Record<string, NetworkLinkRuntime>;
  summaries: Record<string, NetworkInterfaceSummary>;
  removeLinkIds: string[];
}

export interface NetworkTopologyRuntimeBatcher {
  pushMetrics: (nodeId: string, metrics: NetworkMetricRuntime[]) => void;
  pushLink: (link: NetworkLinkRuntime) => void;
  pushSummaries: (summaries: Record<string, NetworkInterfaceSummary>) => void;
  removeLink: (linkId: string) => void;
  flush: () => void;
  clear: () => void;
  dispose: () => void;
}

const emptyPending = (): NetworkTopologyRuntimePending => ({
  metrics: {},
  links: {},
  summaries: {},
  removeLinkIds: [],
});

const isPendingEmpty = (pending: NetworkTopologyRuntimePending): boolean =>
  Object.keys(pending.metrics).length === 0 &&
  Object.keys(pending.links).length === 0 &&
  Object.keys(pending.summaries).length === 0 &&
  pending.removeLinkIds.length === 0;

export const createNetworkTopologyRuntimeBatcher = (options: {
  apply: (pending: NetworkTopologyRuntimePending) => void;
  flushMs?: number;
}): NetworkTopologyRuntimeBatcher => {
  const flushMs = options.flushMs ?? NETWORK_TOPOLOGY_RUNTIME_FLUSH_MS;
  let pending = emptyPending();
  let timer: ReturnType<typeof setTimeout> | null = null;

  const flush = () => {
    if (timer != null) {
      clearTimeout(timer);
      timer = null;
    }
    if (isPendingEmpty(pending)) return;
    const snapshot = pending;
    pending = emptyPending();
    options.apply(snapshot);
  };

  const schedule = () => {
    if (timer != null) return;
    timer = setTimeout(flush, flushMs);
  };

  const clearTimer = () => {
    if (timer != null) {
      clearTimeout(timer);
      timer = null;
    }
  };

  return {
    pushMetrics: (nodeId, metrics) => {
      pending.metrics[nodeId] = metrics;
      schedule();
    },
    pushLink: (link) => {
      pending.links[link.id] = link;
      pending.removeLinkIds = pending.removeLinkIds.filter((id) => id !== link.id);
      schedule();
    },
    pushSummaries: (summaries) => {
      pending.summaries = { ...pending.summaries, ...summaries };
      schedule();
    },
    removeLink: (linkId) => {
      delete pending.links[linkId];
      if (!pending.removeLinkIds.includes(linkId)) {
        pending.removeLinkIds.push(linkId);
      }
      schedule();
    },
    flush,
    clear: () => {
      clearTimer();
      pending = emptyPending();
    },
    dispose: () => {
      clearTimer();
      pending = emptyPending();
    },
  };
};
