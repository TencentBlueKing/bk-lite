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
  let rooms: Room3DRoomOption[] = [];
  try {
    const payload: unknown = await api.getRooms(signal);
    const record =
      payload && typeof payload === 'object'
        ? (payload as { items?: unknown })
        : null;
    const raw = Array.isArray(payload)
      ? payload
      : record && Array.isArray(record.items)
        ? record.items
        : [];
    rooms = raw.flatMap((item) => {
      if (!item || typeof item !== 'object') return [];
      const row = item as { id?: unknown; name?: unknown; inst_uuid?: unknown; inst_name?: unknown };
      const id = typeof row.id === 'string'
        ? row.id
        : typeof row.inst_uuid === 'string'
          ? row.inst_uuid
          : '';
      if (!id) return [];
      const name = typeof row.name === 'string'
        ? row.name
        : typeof row.inst_name === 'string'
          ? row.inst_name
          : id;
      return [{ id, name }];
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    const explicitId = [runtimeRoomId, savedRoomId].some(
      (value) => typeof value === 'string' && value.trim(),
    );
    if (!explicitId) throw error;
  }
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
