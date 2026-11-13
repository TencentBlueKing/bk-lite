import { useCallback } from 'react';
import { usePathname } from 'next/navigation';
import useApiClient from '@/utils/request';
import { delegatedSceneBase } from './displayDelegate';
import type { ApplicationTopologyResponse } from '@/app/ops-analysis/components/widgets/applicationTopology/types';

export const APPLICATION_TOPOLOGY_API_PATH =
  '/operation_analysis/api/scene_widgets/application_topology/';

export const applicationTopologyApiPath = (
  shareSessionId?: string,
  pathname?: string | null,
) => delegatedSceneBase(
  pathname,
  shareSessionId,
  'application_topology/',
  APPLICATION_TOPOLOGY_API_PATH,
);

export const useApplicationTopologyApi = (shareSessionId?: string) => {
  const { post } = useApiClient();
  const path = applicationTopologyApiPath(shareSessionId, usePathname());

  const getApplicationTopology = useCallback(
    (instUuid: string, depth: number) =>
      post<ApplicationTopologyResponse>(
        path,
        { inst_uuid: instUuid, depth },
        { suppressErrorNotification: true },
      ),
    [path, post],
  );

  return { getApplicationTopology };
};
