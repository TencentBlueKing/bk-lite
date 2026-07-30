'use client';

import { createContext, useContext } from 'react';
import type { NetworkTopologyConfig, NetworkTopologyLink } from '@/app/ops-analysis/types/networkTopology';
import type { NetworkLinkRuntime, NetworkMetricRuntime, NetworkNodeRuntime } from '@/app/ops-analysis/types/networkTopology';

export interface SharedNetworkTopologyRuntimeAccess {
  getMetricValues: (
    items: Array<{
      request_id: string;
      node_ref: Record<string, unknown>;
      metric_ref: { metric_field: string; result_table_id: string };
      dimensions?: Record<string, string>;
      condition_filter?: Array<{ dimension_id: string; value: string[] }>;
      display_mode?: 'aggregate' | 'dimension';
      aggregate_type?: 'sum' | 'max' | 'min' | 'mean' | 'last';
    }>,
  ) => Promise<{ items?: NetworkMetricRuntime[] }>;
  getLinkRuntime: (payload: {
    link: NetworkTopologyLink;
    nodes: NetworkTopologyConfig['nodes'];
  }) => Promise<{
    link?: NetworkLinkRuntime | null;
    node_interface_summary?: Record<
      string,
      NonNullable<NetworkNodeRuntime['interface_summary']>
    >;
    errors?: Array<{ code?: string; message?: string; scope?: string }>;
  }>;
}

const ShareNetworkTopologyRuntimeContext =
  createContext<SharedNetworkTopologyRuntimeAccess | null>(null);

export const ShareNetworkTopologyRuntimeProvider =
  ShareNetworkTopologyRuntimeContext.Provider;

export const useSharedNetworkTopologyRuntime = () =>
  useContext(ShareNetworkTopologyRuntimeContext);
