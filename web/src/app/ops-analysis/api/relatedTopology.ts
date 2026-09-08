import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { RelatedTopologyResponse } from '@/app/ops-analysis/components/widgets/relatedTopology/types';

export const RELATED_TOPOLOGY_API_PATH =
  '/operation_analysis/api/scene_widgets/related_topology/';

export const useRelatedTopologyApi = () => {
  const { post } = useApiClient();

  const getRelatedTopology = useCallback(
    (instUuid: string) =>
      post<RelatedTopologyResponse>(
        RELATED_TOPOLOGY_API_PATH,
        { inst_uuid: instUuid },
        { suppressErrorNotification: true },
      ),
    [post],
  );

  return { getRelatedTopology };
};
