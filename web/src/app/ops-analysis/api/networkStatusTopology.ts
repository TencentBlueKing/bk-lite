import { useCallback } from 'react';
import { usePathname } from 'next/navigation';
import useApiClient from '@/utils/request';
import type { NetworkStatusTopologyResponse } from '@/app/ops-analysis/types/sceneWidget';
import { networkStatusTopologyApiPath } from './displayDelegate';

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
  const pathname = usePathname();
  const path = networkStatusTopologyApiPath(pathname);

  const getNetworkStatusTopology = useCallback(
    (params: NetworkStatusTopologyRequest) =>
      post<NetworkStatusTopologyResponse>(
        path,
        params,
        { suppressErrorNotification: true },
      ),
    [path, post],
  );

  return {
    getNetworkStatusTopology,
  };
};
