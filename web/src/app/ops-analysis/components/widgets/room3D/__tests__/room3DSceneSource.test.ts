import { describe, expect, it, vi } from 'vitest';
import type { Room3DTransport } from '@/app/ops-analysis/api/room3D';
import { loadRoom3DScene } from '../room3DSceneSource';

const ROOM_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const ROOM_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const ROOM_C = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';

const rooms = [
  { id: ROOM_A, name: '机房 A' },
  { id: ROOM_B, name: '机房 B' },
];

const layoutA = {
  room: { id: ROOM_A, name: '机房 A' },
  racks: [{ rack_id: 'r1', rack_name: 'R1', row: 1, col: 1 }],
};

const createApi = (
  overrides?: Partial<Room3DTransport>,
): Room3DTransport => ({
  getRooms: vi.fn(async () => ({ items: rooms })),
  getLayout: vi.fn(async (serverRoomId: string) => ({
    ...layoutA,
    room: { id: serverRoomId, name: serverRoomId },
  })),
  ...overrides,
});

describe('loadRoom3DScene', () => {
  it('loads the first visible room when no default is saved', async () => {
    const api = createApi();
    const result = await loadRoom3DScene({ api, savedRoomId: '' });

    expect(result).toEqual({
      status: 'ready',
      roomId: ROOM_A,
      rooms,
      layout: { ...layoutA, room: { id: ROOM_A, name: ROOM_A } },
    });
    expect(api.getLayout).toHaveBeenCalledWith(ROOM_A, undefined);
  });

  it('does not fetch layout when the pinned default is unavailable', async () => {
    const api = createApi();
    const result = await loadRoom3DScene({ api, savedRoomId: ROOM_C });

    expect(result).toEqual({ status: 'unavailable', rooms });
    expect(api.getLayout).not.toHaveBeenCalled();
  });

  it('uses an ephemeral runtime room even when the default is unavailable', async () => {
    const api = createApi();
    const result = await loadRoom3DScene({
      api,
      savedRoomId: ROOM_C,
      runtimeRoomId: ROOM_B,
    });

    expect(result.status).toBe('ready');
    expect(result).toMatchObject({ roomId: ROOM_B });
    expect(api.getLayout).toHaveBeenCalledWith(ROOM_B, undefined);
  });

  it('returns empty without fetching layout when no room is visible', async () => {
    const api = createApi({
      getRooms: vi.fn(async () => ({ items: [] })),
    });
    const result = await loadRoom3DScene({ api, savedRoomId: ROOM_A });

    expect(result).toEqual({ status: 'empty', rooms: [] });
    expect(api.getLayout).not.toHaveBeenCalled();
  });
});
