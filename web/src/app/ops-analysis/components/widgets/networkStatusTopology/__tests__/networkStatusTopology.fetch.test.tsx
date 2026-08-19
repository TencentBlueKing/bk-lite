// @vitest-environment jsdom

import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { HandledRequestError } from '@/utils/request';

const testState = vi.hoisted(() => ({
  getNetworkStatusTopology: vi.fn(),
  translate: (key: string) => key,
}));

const overlayState = vi.hoisted(() => ({
  getSourceDataByApiId: vi.fn(),
  getDataSourceBriefList: vi.fn(),
  dataSources: [
    { id: 31, rest_api: 'cmdb/get_monitor_ids_by_inst_uuids', is_build_in: true },
    { id: 32, rest_api: 'monitor/query_latest_active_alerts', is_build_in: true },
  ],
  shareMode: false,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: testState.translate }),
}));

vi.mock('@/app/ops-analysis/context/shareMode', () => ({
  useShareMode: () => overlayState.shareMode,
}));

vi.mock('@/app/ops-analysis/context/common', () => ({
  useOpsAnalysis: () => ({
    dataSources: overlayState.dataSources,
  }),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getSourceDataByApiId: (...args: unknown[]) =>
      overlayState.getSourceDataByApiId(...args),
    getDataSourceBriefList: (...args: unknown[]) =>
      overlayState.getDataSourceBriefList(...args),
  }),
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
  NetworkTopologyX6Canvas: ({
    data,
    toolbar,
    onNodeClick,
    onNodeContextMenu,
    onNodeMouseEnter,
    onNodeMouseLeave,
  }: {
    data: { nodes?: Array<{ id: string; status?: string }> };
    toolbar?: { onRefresh?: () => void };
    onNodeClick?: (nodeId: string, event?: MouseEvent) => void;
    onNodeContextMenu?: (nodeId: string, event: MouseEvent) => void;
    onNodeMouseEnter?: (nodeId: string, event: MouseEvent) => void;
    onNodeMouseLeave?: (nodeId: string) => void;
  }) => (
    <div data-testid="status-topo-canvas">
      {(data.nodes || []).map((node) => node.id).join(',')}
      {(data.nodes || []).map((node) => (
        <span key={`st-${node.id}`} data-testid={`status-topo-status-${node.id}`}>
          {node.status || 'none'}
        </span>
      ))}
      {(data.nodes || []).map((node) => (
        <button
          key={`node-${node.id}`}
          type="button"
          data-testid={`status-topo-node-${node.id}`}
          onClick={(event) => onNodeClick?.(node.id, event.nativeEvent)}
          onMouseEnter={(event) => onNodeMouseEnter?.(node.id, event.nativeEvent)}
          onMouseLeave={() => onNodeMouseLeave?.(node.id)}
          onContextMenu={(event) => {
            event.preventDefault();
            onNodeContextMenu?.(node.id, {
              preventDefault: () => undefined,
              offsetX: 12,
              offsetY: 12,
            } as MouseEvent);
          }}
        >
          {`node-${node.id}`}
        </button>
      ))}
      {(data.nodes || []).map((node) => (
        <button
          key={`badge-${node.id}`}
          type="button"
          className="status-topo-alert-badge"
          data-testid={`status-topo-badge-${node.id}`}
          onClick={(event) => onNodeClick?.(node.id, event.nativeEvent)}
        >
          {`badge-${node.id}`}
        </button>
      ))}
      <button
        type="button"
        data-testid="status-topo-refresh"
        onClick={toolbar?.onRefresh}
      >
        refresh
      </button>
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
  isStatusTopologyIconHoverTarget: () => true,
  isStatusTopologyBadgeTarget: (event: MouseEvent) =>
    Boolean((event.target as HTMLElement | null)?.classList?.contains('status-topo-alert-badge')),
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

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

const widgetConfig = {
  networkStatusTopology: {
    modelId: 'switch',
    instUuid: '123e4567-e89b-42d3-a456-426614174000',
    depth: 2,
  },
};

const successPayload = {
  center_id: 'core-1',
  nodes: [{ id: 'core-1', model_id: 'switch', name: 'Core' }],
  links: [],
};

const defaultOverlaySources = [
  { id: 31, rest_api: 'cmdb/get_monitor_ids_by_inst_uuids', is_build_in: true },
  { id: 32, rest_api: 'monitor/query_latest_active_alerts', is_build_in: true },
];

const defaultGetSourceDataByApiId = (
  id: number,
  params?: Record<string, unknown>,
) => {
  if (id === 31) {
    const uuids = Array.isArray(params?.inst_uuids)
      ? (params?.inst_uuids as string[])
      : [];
    return Promise.resolve({
      data: {
        items: uuids.map((inst_uuid) => ({
          inst_uuid,
          model_id: 'switch',
          monitor_id: '',
        })),
      },
      warnings: [],
    });
  }
  return Promise.resolve({
    data: { count: 0, max_level: null, items: [], instance_summaries: [] },
    warnings: [],
  });
};

const overlayParamsFor = (id: number) =>
  overlayState.getSourceDataByApiId.mock.calls
    .filter(([calledId]) => calledId === id)
    .map(([, params]) => params);

const mockMonitoredCriticalOverlay = () => {
  overlayState.getSourceDataByApiId.mockImplementation(
    (id: number, params?: Record<string, unknown>) => {
      if (id === 31) {
        return Promise.resolve({
          data: {
            items: [{ inst_uuid: 'core-1', model_id: 'switch', monitor_id: 'mon-core' }],
          },
          warnings: [],
        });
      }
      if (params?.limit === 1) {
        return Promise.resolve({
          data: {
            count: 5,
            max_level: 'critical',
            items: [{
              id: 'stale-item',
              content: 'should-not-appear',
              level: 'critical',
              alert_type: 'threshold',
              start_event_time: '2020-01-01T00:00:00Z',
            }],
            instance_summaries: [{
              instance_id: 'mon-core',
              count: 5,
              max_level: 'critical',
            }],
          },
          warnings: [],
        });
      }
      return Promise.resolve({
        data: {
          count: 5,
          max_level: 'critical',
          items: [{
            id: 'a1',
            content: 'cpu high',
            level: 'critical',
            alert_type: 'threshold',
            start_event_time: '2026-08-19T01:00:00Z',
          }],
          instance_summaries: [{
            instance_id: 'mon-core',
            count: 5,
            max_level: 'critical',
          }],
        },
        warnings: [],
      });
    },
  );
};

beforeEach(() => {
  overlayState.dataSources = [...defaultOverlaySources];
  overlayState.shareMode = false;
  overlayState.getSourceDataByApiId.mockReset();
  overlayState.getDataSourceBriefList.mockReset();
  overlayState.getSourceDataByApiId.mockImplementation(defaultGetSourceDataByApiId);
  overlayState.getDataSourceBriefList.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  testState.getNetworkStatusTopology.mockReset();
});

describe('networkStatusTopology owner requests', () => {
  it('does not refetch when scrolling only changes runtime priority', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    const { rerender } = render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
        runtimePriority={{ cause: 1, visibility: 1, distance: 300, order: 2 }}
      />,
    );
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(1);
    });

    rerender(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
        runtimePriority={{ cause: 1, visibility: 0, distance: 0, order: 2 }}
      />,
    );
    await Promise.resolve();
    expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(1);
  });

  it('refetches when the toolbar refresh is clicked after a successful load', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(screen.getByTestId('status-topo-refresh'));
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(2);
    });
  });

  it('retries when refresh is clicked after a failed load', async () => {
    testState.getNetworkStatusTopology
      .mockRejectedValueOnce(new HandledRequestError('拓扑刷新失败'))
      .mockResolvedValueOnce(successPayload);

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(screen.getByText('拓扑刷新失败')).toBeTruthy();
    });
    expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByText('dashboard.networkTopoRefresh'));
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('core-1');
    });
  });

  it.each([
    undefined,
    '',
    'undefined',
    'legacy-id',
    '123e4567-e89b-12d3-a456-426614174000',
    '123E4567-E89B-42D3-A456-426614174000',
  ])(
    'does not request topology for invalid instUuid %s',
    async (instUuid) => {
      render(
        <NetworkStatusTopology
          config={{
            networkStatusTopology: {
              modelId: 'switch',
              instUuid,
              depth: 2,
            },
          }}
          refreshKey="0"
          refreshCause="initial"
        />,
      );

      await waitFor(() => {
        expect(screen.getByText('dashboard.networkTopoMissingConfig')).toBeTruthy();
      });
      expect(testState.getNetworkStatusTopology).not.toHaveBeenCalled();
    },
  );

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

describe('networkStatusTopology monitor overlay', () => {
  it('fetches mapping then monitor summaries after topology success', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    overlayState.getSourceDataByApiId.mockImplementation(
      (id: number) => {
        if (id === 31) {
          return Promise.resolve({
            data: {
              items: [{ inst_uuid: 'core-1', model_id: 'switch', monitor_id: 'mon-core' }],
            },
            warnings: [],
          });
        }
        return Promise.resolve({
          data: {
            count: 0,
            max_level: null,
            items: [],
            instance_summaries: [{ instance_id: 'mon-core', count: 0, max_level: null }],
          },
          warnings: [],
        });
      },
    );

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(overlayParamsFor(31)).toEqual([{ inst_uuids: ['core-1'] }]);
    });
    await waitFor(() => {
      expect(overlayParamsFor(32)).toEqual([{ instance_ids: ['mon-core'], limit: 1 }]);
    });
    expect(overlayState.getDataSourceBriefList).not.toHaveBeenCalled();
  });

  it('shows unmonitored copy in the popover instead of 0', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('core-1');
    });
    await waitFor(() => {
      expect(overlayParamsFor(31).length).toBeGreaterThan(0);
    });

    fireEvent.mouseEnter(screen.getByTestId('status-topo-node-core-1'));
    const alertsLine = await screen.findByTestId('status-topo-popover-alerts');
    expect(alertsLine.textContent).toContain('dashboard.networkTopoUnmonitored');
    expect(alertsLine.textContent).not.toMatch(/\b0\b/);
  });

  it('keeps topology nodes and retries overlay only when NATS overlay fails', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    overlayState.getSourceDataByApiId
      .mockRejectedValueOnce(new Error('nats down'))
      .mockImplementation(defaultGetSourceDataByApiId);

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-topo-canvas').textContent).toContain('core-1');
    });
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-overlay-error')).toBeTruthy();
    });
    expect(screen.getByText('dashboard.networkTopoStatusLoadFailed')).toBeTruthy();
    expect(screen.getByTestId('status-topo-status-core-1').textContent).toBe('unknown');
    expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(1);

    fireEvent.click(
      within(screen.getByTestId('status-topo-overlay-error')).getByRole('button'),
    );
    await waitFor(() => {
      expect(overlayState.getSourceDataByApiId.mock.calls.length).toBeGreaterThan(1);
    });
    expect(testState.getNetworkStatusTopology).toHaveBeenCalledTimes(1);
  });

  it('opens the alert modal with a fresh limit-10 query from the context menu', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    mockMonitoredCriticalOverlay();

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(overlayParamsFor(32)).toContainEqual({
        instance_ids: ['mon-core'],
        limit: 1,
      });
    });

    fireEvent.contextMenu(screen.getByTestId('status-topo-node-core-1'));
    fireEvent.click(screen.getByText('dashboard.networkTopoViewAlerts'));

    await waitFor(() => {
      expect(overlayParamsFor(32)).toContainEqual({
        instance_ids: ['mon-core'],
        limit: 10,
      });
    });
    await waitFor(() => {
      expect(screen.getByText('cpu high')).toBeTruthy();
    });
    expect(screen.queryByText('should-not-appear')).toBeNull();
    expect(screen.getByText(/dashboard.networkTopoLatestItems/)).toBeTruthy();
  });

  it('disables instance detail in share mode but still allows viewing alerts', async () => {
    overlayState.shareMode = true;
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    mockMonitoredCriticalOverlay();

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(overlayParamsFor(32)).toContainEqual({
        instance_ids: ['mon-core'],
        limit: 1,
      });
    });

    fireEvent.contextMenu(screen.getByTestId('status-topo-node-core-1'));
    expect(
      screen.getByText('dashboard.networkTopoInstanceDetail').closest('button'),
    ).toHaveProperty('disabled', true);
    const viewAlerts = screen.getByText('dashboard.networkTopoViewAlerts').closest('button');
    expect(viewAlerts).toHaveProperty('disabled', false);

    fireEvent.click(viewAlerts as HTMLButtonElement);
    await waitFor(() => {
      expect(overlayParamsFor(32)).toContainEqual({
        instance_ids: ['mon-core'],
        limit: 10,
      });
    });
  });

  it('calls onReady when topology has nodes without waiting for overlay', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    overlayState.getSourceDataByApiId.mockImplementation(
      () => new Promise(() => undefined),
    );
    const onReady = vi.fn();

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
        onReady={onReady}
      />,
    );

    await waitFor(() => {
      expect(onReady).toHaveBeenCalledWith(true);
    });
    expect(screen.getByTestId('status-topo-canvas').textContent).toContain('core-1');
    expect(overlayParamsFor(32)).toEqual([]);
  });

  it('shows 0 for monitored quiet nodes and does not open the alert modal', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    overlayState.getSourceDataByApiId.mockImplementation(
      (id: number) => {
        if (id === 31) {
          return Promise.resolve({
            data: {
              items: [{ inst_uuid: 'core-1', model_id: 'switch', monitor_id: 'mon-core' }],
            },
            warnings: [],
          });
        }
        return Promise.resolve({
          data: {
            count: 0,
            max_level: null,
            items: [],
            instance_summaries: [{ instance_id: 'mon-core', count: 0, max_level: null }],
          },
          warnings: [],
        });
      },
    );

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-topo-status-core-1').textContent).toBe('normal');
    });

    fireEvent.mouseEnter(screen.getByTestId('status-topo-node-core-1'));
    const alertsLine = await screen.findByTestId('status-topo-popover-alerts');
    expect(alertsLine.textContent).toMatch(/\b0\b/);
    expect(alertsLine.querySelector('button')).toBeNull();

    fireEvent.contextMenu(screen.getByTestId('status-topo-node-core-1'));
    expect(
      screen.getByText('dashboard.networkTopoViewAlerts').closest('button'),
    ).toHaveProperty('disabled', true);

    fireEvent.click(screen.getByTestId('status-topo-badge-core-1'));
    expect(overlayParamsFor(32).some((params) => params?.limit === 10)).toBe(false);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('opens the alert modal from the badge with a fresh limit-10 query', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    mockMonitoredCriticalOverlay();

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-status-core-1').textContent).toBe('critical');
    });

    fireEvent.click(screen.getByTestId('status-topo-badge-core-1'));
    await waitFor(() => {
      expect(overlayParamsFor(32)).toContainEqual({
        instance_ids: ['mon-core'],
        limit: 10,
      });
    });
    await waitFor(() => {
      expect(screen.getByText('cpu high')).toBeTruthy();
    });
    expect(screen.queryByText('should-not-appear')).toBeNull();
  });

  it('keeps the popover open across the icon gap so the alert count can be clicked', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    mockMonitoredCriticalOverlay();

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('status-topo-status-core-1').textContent).toBe('critical');
    });

    fireEvent.mouseEnter(screen.getByTestId('status-topo-node-core-1'));
    await screen.findByTestId('status-topo-popover-alerts');
    fireEvent.mouseLeave(screen.getByTestId('status-topo-node-core-1'));
    fireEvent.mouseEnter(screen.getByTestId('status-topo-popover-layer'));
    fireEvent.click(
      within(screen.getByTestId('status-topo-popover-alerts')).getByRole('button'),
    );

    await waitFor(() => {
      expect(overlayParamsFor(32)).toContainEqual({
        instance_ids: ['mon-core'],
        limit: 10,
      });
    });
  });

  it('does not load the unauthenticated data-source brief list in share mode', async () => {
    overlayState.shareMode = true;
    overlayState.dataSources = [];
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-topo-overlay-error')).toBeTruthy();
    });
    expect(overlayState.getDataSourceBriefList).not.toHaveBeenCalled();
    expect(screen.getByTestId('status-topo-status-core-1').textContent).toBe('unknown');
  });
});

