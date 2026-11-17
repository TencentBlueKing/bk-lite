// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ROOM3D_FILTER_ID } from '@/app/ops-analysis/utils/room3DScreenFilter';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';

const ROOM_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const ROOM_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const { getRooms, getLayout, translate } = vi.hoisted(() => ({
  getRooms: vi.fn(async () => ({
    items: [
      { id: ROOM_A, name: '机房A' },
      { id: ROOM_B, name: '机房B' },
    ],
  })),
  getLayout: vi.fn(async (serverRoomId: string) => ({
    room: { id: serverRoomId, name: serverRoomId },
    racks: [{ rack_id: 'r1', rack_name: 'R1', row: 1, col: 1 }],
  })),
  translate: (key: string) => key,
}));

vi.mock('../room3DScene', () => ({
  createRoom3DScene: vi.fn(() => ({
    resetView: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  })),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: translate }),
}));

vi.mock('@/app/ops-analysis/api/room3D', () => ({
  useRoom3DApi: () => ({ getRooms, getLayout }),
}));

vi.mock('@/app/ops-analysis/context/shareMode', () => ({
  useShareMode: () => false,
}));

vi.mock('next/navigation', () => ({
  useParams: () => ({}),
}));

import Room3D from '../index';

const roomFilter = (
  overrides: Partial<UnifiedFilterDefinition> = {},
): UnifiedFilterDefinition => ({
  id: ROOM3D_FILTER_ID,
  key: 'server_room_id',
  name: '机房',
  type: 'string',
  defaultValue: null,
  order: 0,
  enabled: true,
  ...overrides,
});

describe('Room3D builtin filter load gate', () => {
  afterEach(() => {
    cleanup();
    getRooms.mockClear();
    getLayout.mockClear();
  });

  it('waits for a room instead of loading the first visible one', async () => {
    const view = render(
      <Room3D
        filterDefinitions={[roomFilter()]}
        unifiedFilterValues={{}}
        runtimeActive
      />,
    );

    await waitFor(() => {
      expect(view.getByText('dashboard.room3DSelectRoom')).toBeTruthy();
    });
    expect(getRooms).not.toHaveBeenCalled();
    expect(getLayout).not.toHaveBeenCalled();

    view.rerender(
      <Room3D
        filterDefinitions={[roomFilter()]}
        unifiedFilterValues={{}}
        runtimeActive
      />,
    );

    expect(getLayout).not.toHaveBeenCalled();
  });

  it('keeps a saved default load when the filter later applies the same room', async () => {
    const view = render(
      <Room3D
        filterDefinitions={[roomFilter({ defaultValue: ROOM_A })]}
        unifiedFilterValues={{}}
        runtimeActive
      />,
    );

    await waitFor(() => {
      expect(getLayout).toHaveBeenCalledTimes(1);
    });
    expect(getLayout).toHaveBeenCalledWith(ROOM_A, expect.any(AbortSignal));

    view.rerender(
      <Room3D
        filterDefinitions={[roomFilter({ defaultValue: ROOM_A })]}
        unifiedFilterValues={{ [ROOM3D_FILTER_ID]: ROOM_A }}
        runtimeActive
      />,
    );

    await waitFor(() => {
      expect(getLayout).toHaveBeenCalledTimes(1);
    });
  });
});
