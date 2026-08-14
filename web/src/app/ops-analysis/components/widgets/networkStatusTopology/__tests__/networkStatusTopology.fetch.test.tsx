// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HandledRequestError } from '@/utils/request';

const testState = vi.hoisted(() => ({
  getNetworkStatusTopology: vi.fn(),
  translate: (key: string) => key,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: testState.translate }),
}));

vi.mock('@/app/ops-analysis/context/shareMode', () => ({
  useShareMode: () => false,
}));

vi.mock('@/app/ops-analysis/components/widget-viewport', () => ({
  useWidgetViewport: () => ({ scale: 1 }),
}));

vi.mock('@/utils/request', () => {
  class HandledRequestError extends Error {
    constructor(message: string) {
      super(message);
      this.name = 'HandledRequestError';
    }
  }
  return {
    HandledRequestError,
    default: () => ({
      get: vi.fn(),
      post: (...args: unknown[]) => testState.getNetworkStatusTopology(...args),
      put: vi.fn(),
      del: vi.fn(),
    }),
  };
});

vi.mock('@/app/ops-analysis/api/networkStatusTopology', () => ({
  useNetworkStatusTopologyApi: () => ({
    getNetworkStatusTopology: (...args: unknown[]) =>
      testState.getNetworkStatusTopology(...args),
  }),
}));

vi.mock('@/app/cmdb/components/networkTopology', () => ({
  NetworkTopologyX6Canvas: ({ data }: { data: { nodes?: Array<{ id: string }> } }) => (
    <div data-testid="status-topo-canvas">
      {(data.nodes || []).map((node) => node.id).join(',')}
    </div>
  ),
  layoutNetworkTopology: ({ nodes }: { nodes: Array<{ id: string }> }) => ({
    nodes: nodes.map((node) => ({ ...node, x: 0, y: 0 })),
    links: [],
  }),
}));

vi.mock('../statusTopologyGraph', () => ({
  STATUS_TOPOLOGY_NODE_SHAPE: 'topo-network-status-device-test',
  STATUS_TOPOLOGY_PALETTE_DARK: {},
  STATUS_TOPOLOGY_PALETTE_LIGHT: {},
  STATUS_TOPOLOGY_VISUAL: {},
  isStatusTopologyIconHoverTarget: () => false,
  ensureStatusTopologyNodeRegistered: vi.fn(),
  buildStatusTopologyX6GraphData: ({
    nodes,
  }: {
    nodes: Array<{ id: string }>;
  }) => ({
    nodes,
    edges: [],
  }),
}));

import NetworkStatusTopology from '../index';

const widgetConfig = {
  networkStatusTopology: {
    modelId: 'switch',
    instId: 'core-1',
    depth: 2,
  },
};

const successPayload = {
  center_id: 'core-1',
  nodes: [{ id: 'core-1', model_id: 'switch', name: 'Core' }],
  links: [],
};

afterEach(() => {
  cleanup();
  testState.getNetworkStatusTopology.mockReset();
});

describe('networkStatusTopology owner requests', () => {
  it('skips a silent tick while a manual request is in flight and still accepts the manual success', async () => {
    let resolveManual: ((value: typeof successPayload) => void) | undefined;
    testState.getNetworkStatusTopology
      .mockResolvedValueOnce(successPayload)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveManual = resolve;
          }),
      );

    const { rerender } = render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('core-1');
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="1"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(2);
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="2"
        refreshCause="periodic"
      />,
    );
    await Promise.resolve();
    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="3"
        refreshCause="visibility"
      />,
    );
    await Promise.resolve();
    expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(2);

    resolveManual?.({
      ...successPayload,
      nodes: [{ id: 'manual-1', model_id: 'switch', name: 'Manual' }],
    });
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('manual-1');
    });
  });

  it('skips a silent tick while a manual request is in flight and still shows the manual error', async () => {
    let rejectManual: ((reason?: unknown) => void) | undefined;
    testState.getNetworkStatusTopology
      .mockResolvedValueOnce(successPayload)
      .mockImplementationOnce(
        () =>
          new Promise((_, reject) => {
            rejectManual = reject;
          }),
      );

    const { rerender } = render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas')).toBeTruthy();
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="1"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(2);
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="2"
        refreshCause="visibility"
      />,
    );
    await Promise.resolve();
    expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(2);

    rejectManual?.(new HandledRequestError('拓扑刷新失败'));
    await waitFor(() => {
      expect(screen.getByText('拓扑刷新失败')).toBeTruthy();
    });
    expect(screen.queryByTestId('status-topo-canvas')).toBeNull();
  });

  it('lets a manual request become latest while a silent request is in flight', async () => {
    let resolveSilent: ((value: typeof successPayload) => void) | undefined;
    let resolveManual: ((value: typeof successPayload) => void) | undefined;
    testState.getNetworkStatusTopology
      .mockResolvedValueOnce(successPayload)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSilent = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveManual = resolve;
          }),
      );

    const { rerender } = render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('core-1');
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="1"
        refreshCause="periodic"
      />,
    );
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(2);
    });
    expect(screen.queryByRole('img', { hidden: true })).toBeNull();

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="2"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(3);
    });

    resolveSilent?.({
      ...successPayload,
      nodes: [{ id: 'stale-1', model_id: 'switch', name: 'Stale' }],
    });
    await Promise.resolve();
    expect(screen.getByTestId('status-topo-canvas').textContent).toContain('core-1');
    expect(screen.queryByText(/stale-1/)).toBeNull();

    resolveManual?.({
      ...successPayload,
      nodes: [{ id: 'latest-1', model_id: 'switch', name: 'Latest' }],
    });
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('latest-1');
    });
  });

  it('skips the next periodic tick when an older silent request is still in flight after a newer manual completes', async () => {
    let resolveSilent: ((value: typeof successPayload) => void) | undefined;
    let resolveManual: ((value: typeof successPayload) => void) | undefined;
    testState.getNetworkStatusTopology
      .mockResolvedValueOnce(successPayload)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSilent = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveManual = resolve;
          }),
      );

    const { rerender } = render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('core-1');
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="1"
        refreshCause="periodic"
      />,
    );
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(2);
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="2"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(3);
    });

    resolveManual?.({
      ...successPayload,
      nodes: [{ id: 'latest-1', model_id: 'switch', name: 'Latest' }],
    });
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('latest-1');
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="3"
        refreshCause="periodic"
      />,
    );
    await Promise.resolve();
    expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(3);

    resolveSilent?.({
      ...successPayload,
      nodes: [{ id: 'stale-1', model_id: 'switch', name: 'Stale' }],
    });
    await Promise.resolve();
    expect(screen.getByTestId('status-topo-canvas').textContent).toContain('latest-1');
  });

  it('skips a visibility tick when an older manual request is still in flight after a newer manual completes', async () => {
    let resolveOlder: ((value: typeof successPayload) => void) | undefined;
    let resolveNewer: ((value: typeof successPayload) => void) | undefined;
    testState.getNetworkStatusTopology
      .mockResolvedValueOnce(successPayload)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOlder = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveNewer = resolve;
          }),
      );

    const { rerender } = render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('core-1');
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="1"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(2);
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="2"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(3);
    });

    resolveNewer?.({
      ...successPayload,
      nodes: [{ id: 'latest-1', model_id: 'switch', name: 'Latest' }],
    });
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('latest-1');
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="3"
        refreshCause="visibility"
      />,
    );
    await Promise.resolve();
    expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(3);

    resolveOlder?.({
      ...successPayload,
      nodes: [{ id: 'stale-1', model_id: 'switch', name: 'Stale' }],
    });
    await Promise.resolve();
    expect(screen.getByTestId('status-topo-canvas').textContent).toContain('latest-1');
  });
});
