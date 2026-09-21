import type { Room3DTransport } from '@/app/ops-analysis/api/room3D';
import type { Room3DRoomOption } from '@/app/ops-analysis/types/sceneWidget';
import type { Room3DResponse } from './room3DData';
import {
  resolveRoom3DSelection,
  type Room3DSelection,
} from '@/app/ops-analysis/utils/room3DConfig';

export type Room3DSceneSource =
  | Extract<Room3DSelection, { status: 'empty' | 'unavailable' }>
  | {
      status: 'ready';
      roomId: string;
      rooms: Room3DRoomOption[];
      layout: Room3DResponse;
    };

export const loadRoom3DScene = async ({
  api,
  savedRoomId,
  runtimeRoomId,
  signal,
}: {
  api: Room3DTransport;
  savedRoomId?: string;
  runtimeRoomId?: string;
  signal?: AbortSignal;
}): Promise<Room3DSceneSource> => {
  const payload = await api.getRooms(signal);
  const rooms = Array.isArray(payload?.items) ? payload.items : [];
  const selection = resolveRoom3DSelection({
    rooms,
    savedRoomId,
    runtimeRoomId,
  });
  if (selection.status !== 'ready') {
    return selection;
  }
  const layout = await api.getLayout(selection.roomId, signal);
  return { ...selection, layout };
};
