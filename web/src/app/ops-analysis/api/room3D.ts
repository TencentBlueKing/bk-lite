import { useCallback } from 'react';
import useApiClient from '@/utils/request';

export const ROOM3D_EMBED_API_PATH =
  '/operation_analysis/api/scene_widgets/room3d/';

export const useRoom3DEmbedApi = () => {
  const { post } = useApiClient();

  const getRoom3DLayout = useCallback(
    (instUuid: string) =>
      post(
        ROOM3D_EMBED_API_PATH,
        { inst_uuid: instUuid },
        { suppressErrorNotification: true },
      ),
    [post],
  );

  return { getRoom3DLayout };
};
