import { useCallback } from 'react';
import { usePathname } from 'next/navigation';
import useApiClient from '@/utils/request';
import type { RelatedTopologyResponse } from '@/app/ops-analysis/components/widgets/relatedTopology/types';
import { delegatedSceneBase } from './displayDelegate';

export const RELATED_TOPOLOGY_API_PATH =
  '/operation_analysis/api/scene_widgets/related_topology/';

export const relatedTopologyApiPath = (
  shareSessionId?: string,
  pathname?: string | null,
) => delegatedSceneBase(
  pathname,
  shareSessionId,
  'related_topology/',
  RELATED_TOPOLOGY_API_PATH,
);

export const useRelatedTopologyApi = (shareSessionId?: string) => {
  const { post } = useApiClient();
  const path = relatedTopologyApiPath(shareSessionId, usePathname());

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
