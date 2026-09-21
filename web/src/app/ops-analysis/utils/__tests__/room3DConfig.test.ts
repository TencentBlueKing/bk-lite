import { describe, expect, it } from 'vitest';
import {
  persistRoom3DConfig,
  hydrateRoom3DConfig,
  readPersistedServerRoomId,
  readRoom3DRackTopLines,
  resolveRoom3DSelection,
} from '../room3DConfig';

const ROOM_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const ROOM_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const ROOM_C = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';

const rooms = [
  { id: ROOM_A, name: '机房 A' },
  { id: ROOM_B, name: '机房 B' },
];

describe('persistRoom3DConfig', () => {
  it('keeps a valid default room and drops empty or invalid ids', () => {
    expect(persistRoom3DConfig({ serverRoomId: ROOM_A })).toEqual({
      serverRoomId: ROOM_A,
    });
    expect(persistRoom3DConfig({ serverRoomId: '  ' })).toEqual({});
    expect(persistRoom3DConfig({ serverRoomId: 'not-a-uuid' })).toEqual({});
    expect(persistRoom3DConfig({})).toEqual({});
  });

  it('omits default rack-top lines and keeps non-default choices including an empty second line', () => {
    expect(
      persistRoom3DConfig({
        rackTopLine1: 'location',
        rackTopLine2: 'type',
      }),
    ).toEqual({});
    expect(
      persistRoom3DConfig({
        rackTopLine1: 'name',
        rackTopLine2: 'state',
      }),
    ).toEqual({
      rackTopLine1: 'name',
      rackTopLine2: 'state',
    });
    expect(
      persistRoom3DConfig({
        rackTopLine1: 'location',
        rackTopLine2: '',
      }),
    ).toEqual({
      rackTopLine1: 'location',
      rackTopLine2: '',
    });
    expect(
      persistRoom3DConfig({
        rackTopLine1: 'type',
        rackTopLine2: 'type',
      }),
    ).toEqual({
      rackTopLine1: 'type',
      rackTopLine2: 'type',
    });
  });

  it('recovers both-empty rack-top input to location on the first line', () => {
    expect(
      persistRoom3DConfig({
        rackTopLine1: undefined,
        rackTopLine2: '',
      }),
    ).toEqual({
      rackTopLine1: 'location',
      rackTopLine2: '',
    });
  });
});

describe('readRoom3DRackTopLines', () => {
  it('defaults to location then type when nothing is saved', () => {
    expect(readRoom3DRackTopLines()).toEqual({
      line1: 'location',
      line2: 'type',
    });
    expect(readRoom3DRackTopLines({})).toEqual({
      line1: 'location',
      line2: 'type',
    });
  });

  it('treats a missing second line as hidden once the first line is saved', () => {
    expect(readRoom3DRackTopLines({ rackTopLine1: 'name' })).toEqual({
      line1: 'name',
      line2: '',
    });
    expect(
      readRoom3DRackTopLines({
        rackTopLine1: 'location',
        rackTopLine2: '',
      }),
    ).toEqual({
      line1: 'location',
      line2: '',
    });
  });
});

describe('hydrateRoom3DConfig', () => {
  it('fills default rack-top dropdowns for the config form', () => {
    expect(hydrateRoom3DConfig({ serverRoomId: ROOM_A })).toEqual({
      serverRoomId: ROOM_A,
      rackTopLine1: 'location',
      rackTopLine2: 'type',
    });
    expect(
      hydrateRoom3DConfig({
        rackTopLine1: 'name',
        rackTopLine2: '',
      }),
    ).toEqual({
      rackTopLine1: 'name',
    });
  });
});

describe('readPersistedServerRoomId', () => {
  it('prefers scene config over legacy dataSourceParams', () => {
    expect(
      readPersistedServerRoomId({
        room3D: { serverRoomId: ROOM_A },
        dataSourceParams: [{ name: 'server_room_id', value: ROOM_B }],
      }),
    ).toBe(ROOM_A);
  });

  it('reads legacy dataSourceParams when scene config is empty', () => {
    expect(
      readPersistedServerRoomId({
        chartType: 'room3D',
        dataSource: 12,
        dataSourceParams: [{ name: 'server_room_id', value: ROOM_B }],
      }),
    ).toBe(ROOM_B);
    expect(
      readPersistedServerRoomId({
        dataSourceParams: [{ name: 'server_room_id', value: '' }],
      }),
    ).toBe('');
  });
});

describe('resolveRoom3DSelection', () => {
  it('uses the first visible room when no default is saved', () => {
    expect(resolveRoom3DSelection({ rooms, savedRoomId: '' })).toEqual({
      status: 'ready',
      roomId: ROOM_A,
      rooms,
    });
  });

  it('keeps a saved default that is still visible', () => {
    expect(resolveRoom3DSelection({ rooms, savedRoomId: ROOM_B })).toEqual({
      status: 'ready',
      roomId: ROOM_B,
      rooms,
    });
  });

  it('marks a pinned default unavailable instead of substituting another room', () => {
    expect(resolveRoom3DSelection({ rooms, savedRoomId: ROOM_C })).toEqual({
      status: 'unavailable',
      rooms,
    });
  });

  it('lets an ephemeral runtime switch override an unavailable default', () => {
    expect(
      resolveRoom3DSelection({
        rooms,
        savedRoomId: ROOM_C,
        runtimeRoomId: ROOM_B,
      }),
    ).toEqual({
      status: 'ready',
      roomId: ROOM_B,
      rooms,
    });
  });

  it('returns empty when the actor cannot see any room', () => {
    expect(resolveRoom3DSelection({ rooms: [], savedRoomId: ROOM_A })).toEqual({
      status: 'empty',
      rooms: [],
    });
  });
});
