import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { InteractionSurfaceProvider } from '@/app/ops-analysis/context/interactionSurface';
import { ShareModeProvider } from '@/app/ops-analysis/context/shareMode';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import ApplicationTopologyGraphView from '../graphView';

const openNavigation = vi.hoisted(() => vi.fn());

vi.mock('@/app/ops-analysis/utils/interactionBehavior', async () => {
  const actual = await vi.importActual<typeof import('@/app/ops-analysis/utils/interactionBehavior')>(
    '@/app/ops-analysis/utils/interactionBehavior',
  );
  return { ...actual, openPreparedInteractionNavigation: openNavigation };
});

vi.mock('../detailPanel', () => ({
  default: ({ node }: { node: { id: string; name: string } }) => (
    <div data-testid="topology-detail">{node.id}:{node.name}</div>
  ),
}));

const NODE_ID = '9f3c2a10-6b2e-4d11-9a77-0c1e8b44aa01';
const EDGE_ID = 'system-service';

const linkConfig: ValueConfig = {
  chartType: 'applicationTopology',
  sceneWidgetType: 'applicationTopology',
  interaction: {
    kind: 'data',
    name: '查看 CMDB 详情',
    url: '/cmdb/assetData/detail/baseInfo?model_id=$__data.fields.object.model_id$&inst_uuid=$__data.fields.object.id$&inst_name=$__data.fields.object.name$',
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
});

const renderGraph = ({
  editing = false,
  share = false,
  config = linkConfig,
}: {
  editing?: boolean;
  share?: boolean;
  config?: ValueConfig;
} = {}) => render(
  <IntlProvider locale="zh" messages={{}}>
    <ShareModeProvider value={share}>
      <InteractionSurfaceProvider editing={editing}>
        <ApplicationTopologyGraphView
          centerId="system-1"
          usesScreenTheme
          shareMode={share}
          config={config}
          nodes={[
            {
              id: 'system-1',
              name: '计费系统',
              model_id: 'system',
              app_topo_layer: 'system',
            },
            {
              id: NODE_ID,
              name: '订单服务',
              model_id: 'application',
              app_topo_layer: 'service',
            },
          ]}
          links={[{ id: EDGE_ID, source: 'system-1', target: NODE_ID, asst_id: 'contains' }]}
        />
      </InteractionSurfaceProvider>
    </ShareModeProvider>
  </IntlProvider>,
);

const serviceNode = () => screen.getByRole('button', { name: /订单服务/ });

describe('application topology node links', () => {
  it('opens the detail drawer on left click and keeps the node id', () => {
    renderGraph();
    fireEvent.click(serviceNode());
    expect(screen.getByTestId('topology-detail').textContent).toBe(`${NODE_ID}:订单服务`);
    expect(openNavigation).not.toHaveBeenCalled();
  });

  it('highlights a node without a hover hint and opens the CMDB link from the context menu', () => {
    renderGraph();
    fireEvent.mouseEnter(serviceNode(), { clientX: 48, clientY: 64 });
    expect(document.querySelector('.app3d-link-hover')).toBeNull();
    expect(document.body.textContent).not.toContain('右键打开链接');
    expect(serviceNode().style.outlineStyle).toBe('solid');

    const edge = document.querySelector('svg path');
    expect(edge).toBeTruthy();
    expect(fireEvent.contextMenu(edge as Element)).toBe(true);
    expect(screen.queryByRole('menuitem')).toBeNull();

    expect(fireEvent.contextMenu(serviceNode(), { clientX: 30, clientY: 40 })).toBe(false);
    const item = screen.getByRole('menuitem', { name: '查看 CMDB 详情' });
    expect(item.textContent).toBe('查看 CMDB 详情');
    expect(item.querySelector('.anticon-link')).toBeTruthy();
    expect(document.querySelector('.app3d-link-hover')).toBeNull();
    fireEvent.click(item);
    expect(openNavigation).toHaveBeenCalledWith(
      expect.objectContaining({
        href: `/cmdb/assetData/detail/baseInfo?model_id=application&inst_uuid=${NODE_ID}&inst_name=${encodeURIComponent('订单服务')}`,
      }),
      expect.anything(),
    );
  });

  it('closes the node menu on Escape without opening the link', () => {
    renderGraph();
    fireEvent.contextMenu(serviceNode(), { clientX: 30, clientY: 40 });
    expect(screen.getByRole('menuitem', { name: '查看 CMDB 详情' })).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('menuitem')).toBeNull();
    expect(openNavigation).not.toHaveBeenCalled();
  });

  it('keeps the menu item disabled while editing and hides it when shared', () => {
    const editing = renderGraph({ editing: true });
    fireEvent.mouseEnter(serviceNode(), { clientX: 20, clientY: 20 });
    expect(document.querySelector('.app3d-link-hover')).toBeNull();
    expect(serviceNode().style.outlineStyle).toBe('solid');
    expect(fireEvent.contextMenu(serviceNode())).toBe(false);
    const item = screen.getByRole('menuitem', { name: '查看 CMDB 详情' });
    expect(item.getAttribute('aria-disabled')).toBe('true');
    expect(item.getAttribute('title')).toBe('查看模式下可跳转');
    fireEvent.click(item);
    expect(openNavigation).not.toHaveBeenCalled();

    editing.unmount();
    renderGraph({ share: true });
    fireEvent.mouseEnter(serviceNode(), { clientX: 20, clientY: 20 });
    expect(document.querySelector('.app3d-link-hover')).toBeNull();
    expect(fireEvent.contextMenu(serviceNode())).toBe(false);
    expect(screen.queryByRole('menuitem')).toBeNull();
  });
});
