import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { RelatedTopologyResponse } from '@/app/ops-analysis/components/widgets/relatedTopology/types';

export const RELATED_TOPOLOGY_API_PATH =
  '/operation_analysis/api/scene_widgets/related_topology/';

export const relatedTopologyApiPath = (shareSessionId?: string) =>
  shareSessionId
    ? `/operation_analysis/api/dashboard_share/session/${shareSessionId}/related_topology/`
    : RELATED_TOPOLOGY_API_PATH;

export const useRelatedTopologyApi = (shareSessionId?: string) => {
  const { post } = useApiClient();
  const path = relatedTopologyApiPath(shareSessionId);

  const getRelatedTopology = useCallback(
    (instUuid: string) =>
      post<RelatedTopologyResponse>(
        path,
        { inst_uuid: instUuid },
        { suppressErrorNotification: true },
      ),
    [path, post],
  );

  return { getRelatedTopology };
};
