import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { NetworkStatusTopologyResponse } from '@/app/ops-analysis/types/sceneWidget';

export interface NetworkStatusTopologyRequest {
  inst_uuids: string[];
  node_limit?: number;
  depth?: 1;
}

export function buildNetworkStatusTopologyQuery(input: {
  instUuids: string[];
  nodeLimit: number;
  oneHop?: boolean;
}): NetworkStatusTopologyRequest {
  const request: NetworkStatusTopologyRequest = {
    inst_uuids: input.instUuids,
    node_limit: input.nodeLimit,
  };
  if (input.oneHop === true && input.instUuids.length === 1) {
    request.depth = 1;
  }
  return request;
}

export const useNetworkStatusTopologyApi = () => {
  const { post } = useApiClient();

  const getNetworkStatusTopology = useCallback(
    (params: NetworkStatusTopologyRequest) =>
      post<NetworkStatusTopologyResponse>(
        '/operation_analysis/api/scene_widgets/network_status_topology/',
        params,
        { suppressErrorNotification: true },
      ),
    [post],
  );

  return {
    getNetworkStatusTopology,
  };
};
