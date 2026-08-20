import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { NetworkStatusTopologyResponse } from '@/app/ops-analysis/types/sceneWidget';

interface NetworkStatusTopologyRequest {
  inst_uuids: string[];
  node_limit?: number;
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
