import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { InteractionSurfaceProvider } from '@/app/ops-analysis/context/interactionSurface';
import { ShareModeProvider } from '@/app/ops-analysis/context/shareMode';
import type { ScreenRenderContext, ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import Application3D from '../index';

interface SceneOptions {
  onLinkContextMenu?: (hit: {
    x: number;
    y: number;
    system?: { id: string; name: string; modelId?: string };
  } | null) => void;
  onLinkHover?: unknown;
}

const openNavigation = vi.hoisted(() => vi.fn());
const sceneOptions = vi.hoisted(() => ({ current: null as SceneOptions | null }));

vi.mock('@/app/ops-analysis/utils/interactionBehavior', async () => {
  const actual = await vi.importActual<typeof import('@/app/ops-analysis/utils/interactionBehavior')>(
    '@/app/ops-analysis/utils/interactionBehavior',
  );
  return { ...actual, openPreparedInteractionNavigation: openNavigation };
});

vi.mock('next/navigation', () => ({ useParams: () => ({}) }));

vi.mock('@/app/ops-analysis/api/application3D', () => ({
  useApplication3DApi: () => ({
    getWall: vi.fn().mockResolvedValue({
      items: [],
      filters: [],
      appliedFilters: { system_status: [] },
      refreshedAt: '2026-08-26T00:00:00Z',
      capacity: { actualCount: 0, supportedCount: null },
    }),
    getApplicationDetail: vi.fn(),
    getArchitecture: vi.fn(),
    getAlarmDetail: vi.fn(),
    getMetric: vi.fn(),
  }),
}));

vi.mock('../application3DScene', () => ({
  createApplication3DScene: (_node: unknown, options: SceneOptions) => {
    sceneOptions.current = options;
    return {
      reconcile: vi.fn(),
      resize: vi.fn(),
      dispose: vi.fn(),
      setActive: vi.fn(),
      resetCamera: vi.fn(),
      focus: vi.fn(),
      showArchitecture: vi.fn(),
      hideArchitecture: vi.fn(),
      dismissArchitectureOverlay: vi.fn(),
    };
  },
}));

const screenContext: ScreenRenderContext = {
  enabled: true,
  fitScale: 1,
  screenDensity: 1,
  screenUiScale: 1,
  widgetDensity: 1,
  widgetUiScale: 1,
};

const linkConfig: ValueConfig = {
  chartType: 'application3D',
  sceneWidgetType: 'application3D',
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
  sceneOptions.current = null;
});

const renderWall = async ({
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
          <Application3D
            config={linkConfig}
            refreshKey="0"
            runtimeActive
            screenRenderContext={screenContext}
          />
        </InteractionSurfaceProvider>
      </ShareModeProvider>
    </IntlProvider>,
  );
  await waitFor(() => expect(sceneOptions.current?.onLinkContextMenu).toBeTypeOf('function'));
};

const openMenu = () => {
  act(() => {
    sceneOptions.current?.onLinkContextMenu?.({
      x: 24,
      y: 36,
      system: { id: 'sys-1', name: '门户系统', modelId: 'system' },
    });
  });
};

describe('application3D link menu', () => {
  it('does not show a hover popup and opens the configured link from the context menu', async () => {
    await renderWall();
    expect(sceneOptions.current?.onLinkHover).toBeUndefined();
    expect(document.querySelector('.app3d-link-hover')).toBeNull();
    expect(document.body.textContent).not.toContain('右键打开链接');

    openMenu();
    const item = screen.getByRole('menuitem', { name: '查看 CMDB 详情' });
    expect(item.textContent).toBe('查看 CMDB 详情');
    expect(item.querySelector('.anticon-link')).toBeTruthy();
    fireEvent.click(item);
    expect(openNavigation).toHaveBeenCalledWith(
      expect.objectContaining({ href: '/cmdb/detail' }),
      expect.anything(),
    );
  });

  it('disables the menu while editing and hides it when shared', async () => {
    await renderWall({ editing: true });
    openMenu();
    const item = screen.getByRole('menuitem', { name: '查看 CMDB 详情' });
    expect(item.getAttribute('aria-disabled')).toBe('true');
    expect(item.getAttribute('title')).toBe('查看模式下可跳转');
    fireEvent.click(item);
    expect(openNavigation).not.toHaveBeenCalled();

    cleanup();
    await renderWall({ share: true });
    openMenu();
    expect(screen.queryByRole('menuitem')).toBeNull();
    expect(document.querySelector('.app3d-link-hover')).toBeNull();
  });
});
