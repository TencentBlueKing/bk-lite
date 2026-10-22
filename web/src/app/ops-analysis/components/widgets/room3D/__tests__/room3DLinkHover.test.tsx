import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { InteractionSurfaceProvider } from '@/app/ops-analysis/context/interactionSurface';
import { ShareModeProvider } from '@/app/ops-analysis/context/shareMode';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import Room3D from '../index';

const openNavigation = vi.hoisted(() => vi.fn());
const sceneCallbacks = vi.hoisted(() => ({
  current: null as {
    onHover?: (state: {
      rack: { rack_id: string; rack_name: string; row: number; col: number };
      x: number;
      y: number;
    } | null) => void;
    onDeviceSelect?: (selection: {
      rack: { rack_id: string; rack_name: string; row: number; col: number };
      device: { device_id: string; device_name: string };
    } | null) => void;
    onContextMenu?: (hit: {
      rack: { rack_id: string; rack_name: string; row: number; col: number };
      device?: { device_id: string; device_name: string };
      x: number;
      y: number;
    } | null) => void;
  } | null,
}));

vi.mock('@/app/ops-analysis/utils/interactionBehavior', async () => {
  const actual = await vi.importActual<typeof import('@/app/ops-analysis/utils/interactionBehavior')>(
    '@/app/ops-analysis/utils/interactionBehavior',
  );
  return { ...actual, openPreparedInteractionNavigation: openNavigation };
});

vi.mock('../room3DScene', () => ({
  createRoom3DScene: (
    _mount: HTMLDivElement,
    _data: unknown,
    callbacks: NonNullable<typeof sceneCallbacks.current>,
  ) => {
    sceneCallbacks.current = callbacks;
    return { resetView: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
  },
}));

vi.mock('@/app/ops-analysis/api/room3D', () => ({
  useRoom3DApi: () => ({ getRooms: vi.fn(), getLayout: vi.fn() }),
}));

vi.mock('next/navigation', () => ({ useParams: () => ({}) }));

const rack = { rack_id: 'rack-1', rack_name: 'Rack 1', row: 1, col: 1, u_count: 42 };
const device = { device_id: 'dev-1', device_name: 'srv-1' };
const roomData = {
  room: { id: 'room-1', name: 'Room 1' },
  racks: [rack],
};

const linkConfig: ValueConfig = {
  chartType: 'room3D',
  sceneWidgetType: 'room3D',
  interaction: {
    kind: 'data',
    name: '查看 CMDB 详情',
    url: '/cmdb/detail',
    openMode: 'newTab',
  },
};

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver;
  }
});

afterEach(() => {
  cleanup();
  openNavigation.mockClear();
  sceneCallbacks.current = null;
});

const renderRoom = async ({
  editing = false,
  share = false,
}: {
  editing?: boolean;
  share?: boolean;
} = {}) => {
  render(
    <IntlProvider locale="zh" messages={{}}>
      <ShareModeProvider value={share}>
        <InteractionSurfaceProvider editing={editing}>
          <Room3D rawData={roomData} config={linkConfig} />
        </InteractionSurfaceProvider>
      </ShareModeProvider>
    </IntlProvider>,
  );
  await waitFor(() => expect(sceneCallbacks.current?.onHover).toBeTypeOf('function'));
};

describe('room3D device hover', () => {
  it('shows the rack card without a right-click hint, including after a device is selected', async () => {
    await renderRoom();
    act(() => {
      sceneCallbacks.current?.onHover?.({
        rack,
        x: 40,
        y: 30,
      });
    });
    expect(screen.getByText('Rack 1')).toBeTruthy();
    expect(screen.getByText('dashboard.room3DLocation')).toBeTruthy();
    expect(screen.getByText('42')).toBeTruthy();
    expect(screen.queryByText('srv-1')).toBeNull();
    expect(document.body.textContent).not.toContain('右键打开链接');

    act(() => {
      sceneCallbacks.current?.onDeviceSelect?.({ rack, device });
    });
    expect(screen.getByText('srv-1')).toBeTruthy();
    expect(screen.getByText('dashboard.room3DDeviceName')).toBeTruthy();
    expect(screen.queryByText('dashboard.room3DLocation')).toBeNull();
    expect(document.body.textContent).not.toContain('右键打开链接');
  });

  it('opens the configured link from the context menu in view mode', async () => {
    await renderRoom();
    act(() => {
      sceneCallbacks.current?.onContextMenu?.({ rack, device, x: 30, y: 40 });
    });
    fireEvent.click(screen.getByRole('menuitem', { name: '查看 CMDB 详情' }));
    expect(openNavigation).toHaveBeenCalledWith(
      expect.objectContaining({ href: '/cmdb/detail' }),
      expect.anything(),
    );
  });

  it('disables the menu while editing and hides it when shared', async () => {
    await renderRoom({ editing: true });
    act(() => {
      sceneCallbacks.current?.onContextMenu?.({ rack, device, x: 12, y: 16 });
    });
    const item = screen.getByRole('menuitem', { name: '查看 CMDB 详情' });
    expect(item.getAttribute('aria-disabled')).toBe('true');
    expect(item.getAttribute('title')).toBe('查看模式下可跳转');
    fireEvent.click(item);
    expect(openNavigation).not.toHaveBeenCalled();

    cleanup();
    await renderRoom({ share: true });
    act(() => {
      sceneCallbacks.current?.onContextMenu?.({ rack, device, x: 12, y: 16 });
    });
    expect(screen.queryByRole('menuitem')).toBeNull();
  });
});
