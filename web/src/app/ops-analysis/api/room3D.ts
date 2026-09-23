import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { Room3DRoomsData } from '@/app/ops-analysis/types/sceneWidget';
import type { Room3DResponse } from '@/app/ops-analysis/components/widgets/room3D/room3DData';

export interface Room3DTransport {
  getRooms: (signal?: AbortSignal) => Promise<Room3DRoomsData>;
  getLayout: (serverRoomId: string, signal?: AbortSignal) => Promise<Room3DResponse>;
}

export const useRoom3DApi = (shareSessionId?: string): Room3DTransport => {
  const { post } = useApiClient();
  const basePath = shareSessionId
    ? `/operation_analysis/api/dashboard_share/session/${shareSessionId}/room3d`
    : '/operation_analysis/api/scene_widgets/room3d';
  const requestOptions = { suppressErrorNotification: true } as const;

  const getRooms = useCallback(
    (signal?: AbortSignal) =>
      post<Room3DRoomsData>(`${basePath}/rooms/`, {}, { ...requestOptions, signal }),
    [basePath, post],
  );

  const getLayout = useCallback(
    (serverRoomId: string, signal?: AbortSignal) =>
      post<Room3DResponse>(
        `${basePath}/layout/`,
        { server_room_id: serverRoomId },
        { ...requestOptions, signal },
      ),
    [basePath, post],
  );

  return { getRooms, getLayout };
};
