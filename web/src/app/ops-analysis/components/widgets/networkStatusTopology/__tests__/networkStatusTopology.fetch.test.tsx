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
    { id: 33, rest_api: 'monitor/query_latest_interface_metrics', is_build_in: true },
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
    onEdgeMouseEnter,
    onEdgeMouseLeave,
  }: {
    data: {
      nodes?: Array<{ id: string; status?: string }>;
      links?: Array<{
        id: string;
        sourcePort?: string;
        disconnected?: boolean;
        connectStatus?: 'up' | 'down' | 'unknown';
        sourceTrafficLines?: Array<string | { text?: string }>;
      }>;
    };
    toolbar?: { onRefresh?: () => void };
    onNodeClick?: (nodeId: string, event?: MouseEvent) => void;
    onNodeContextMenu?: (nodeId: string, event: MouseEvent) => void;
    onNodeMouseEnter?: (nodeId: string, event: MouseEvent) => void;
    onNodeMouseLeave?: (nodeId: string) => void;
    onEdgeMouseEnter?: (edgeId: string, event: MouseEvent) => void;
    onEdgeMouseLeave?: (edgeId: string) => void;
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
      {(data.links || []).map((link) => (
        <div key={link.id} data-testid={`status-topo-link-${link.id}`}>
          <span data-testid={`status-topo-link-${link.id}-status`}>
            {link.connectStatus || (link.disconnected ? 'down' : 'unknown')}
          </span>
          {link.disconnected ? (
            <span data-testid={`status-topo-link-${link.id}-cross`}>X</span>
          ) : null}
          <span data-testid={`status-topo-link-${link.id}-source-traffic`}>
            {(link.sourceTrafficLines || [])
              .map((line) => (typeof line === 'string' ? line : line?.text || ''))
              .join('|')}
          </span>
          <button
            type="button"
            className="status-topo-port-label"
            data-port-end="source"
            data-testid={`status-topo-port-${link.id}-source`}
            onMouseEnter={(event) => onEdgeMouseEnter?.(link.id, event.nativeEvent)}
            onMouseLeave={() => onEdgeMouseLeave?.(link.id)}
          >
            {link.sourcePort || 'port'}
          </button>
        </div>
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
  layoutNetworkTopology: ({
    nodes,
    links,
  }: {
    nodes: Array<{ id: string }>;
    links?: Array<{ id: string }>;
  }) => ({
    nodes: nodes.map((node) => ({ ...node, x: 0, y: 0 })),
    links: links || [],
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
  getStatusTopologyPortHoverEnd: (event: MouseEvent) => {
    const el = event.target as HTMLElement | null;
    if (!el?.classList?.contains('status-topo-port-label')) return null;
    const end = el.getAttribute('data-port-end');
    return end === 'source' || end === 'target' ? end : null;
  },
  ensureStatusTopologyNodeRegistered: vi.fn(),
  buildStatusTopologyX6GraphData: ({
    nodes,
    links,
  }: {
    nodes: Array<{ id: string }>;
    links?: Array<{ id: string }>;
  }) => ({
    nodes,
    edges: [],
    links: links || [],
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
    instUuids: ['123e4567-e89b-42d3-a456-426614174000'],
    nodeLimit: 100,
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
  { id: 33, rest_api: 'monitor/query_latest_interface_metrics', is_build_in: true },
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
  if (id === 33) {
    return Promise.resolve({
      data: { items: [] },
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
      if (id === 33) {
        return Promise.resolve({
          data: { items: [] },
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
    expect(testState.getNetworkStatusTopology).toHaveBeenCalledWith({
      inst_uuids: ['123e4567-e89b-42d3-a456-426614174000'],
      node_limit: 100,
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
    { instUuids: undefined, modelId: 'switch', instUuid: '123e4567-e89b-42d3-a456-426614174000', depth: 2 },
    { instUuids: [] },
  ])(
    'does not request topology when device list is missing',
    async (topology) => {
      render(
        <NetworkStatusTopology
          config={{
            networkStatusTopology: topology,
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
    await waitFor(() => {
      expect(overlayParamsFor(33)).toEqual([{ instance_ids: ['mon-core'] }]);
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

  it('reports fetched topology payload for preview raw data', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(successPayload);
    overlayState.getSourceDataByApiId.mockImplementation(
      () => new Promise(() => undefined),
    );
    const onRawData = vi.fn();

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
        onRawData={onRawData}
      />,
    );

    await waitFor(() => {
      const payload = onRawData.mock.calls.at(-1)?.[0] as {
        nodes?: Array<{ id: string }>;
      };
      expect(payload?.nodes?.some((node) => node.id === 'core-1')).toBe(true);
    });
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

describe('networkStatusTopology link runtime', () => {
  const linkedPayload = {
    center_id: 'core-1',
    nodes: [
      { id: 'core-1', model_id: 'switch', name: 'Core' },
      { id: 'acc-1', model_id: 'switch', name: 'Acc' },
    ],
    links: [{
      id: 'l1',
      source: 'core-1',
      target: 'acc-1',
      source_port: 'Gi0/1',
      target_port: 'Gi0/2',
    }],
  };

  const quietSummaries = {
    data: {
      count: 0,
      max_level: null,
      items: [],
      instance_summaries: [
        { instance_id: 'mon-core', count: 0, max_level: null },
        { instance_id: 'mon-acc', count: 0, max_level: null },
      ],
    },
    warnings: [],
  };

  const mockLinkedOverlay = (options?: {
    items?: Array<Record<string, unknown>>;
    interfaceFail?: boolean;
  }) => {
    overlayState.getSourceDataByApiId.mockImplementation((id: number) => {
      if (id === 31) {
        return Promise.resolve({
          data: {
            items: [
              { inst_uuid: 'core-1', model_id: 'switch', monitor_id: 'mon-core' },
              { inst_uuid: 'acc-1', model_id: 'switch', monitor_id: 'mon-acc' },
            ],
          },
          warnings: [],
        });
      }
      if (id === 33) {
        if (options?.interfaceFail) {
          return Promise.reject(new Error('interface nats down'));
        }
        return Promise.resolve({
          data: { items: options?.items || [] },
          warnings: [],
        });
      }
      return Promise.resolve(quietSummaries);
    });
  };

  it('marks a down port with a cross and inbound traffic under the name', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(linkedPayload);
    mockLinkedOverlay({
      items: [
        {
          instance_id: 'mon-core',
          ifDescr: 'GigabitEthernet0/1',
          metrics: {
            interface_ifOperStatus: 1,
            interface_ifHCInOctets: 8,
          },
        },
        {
          instance_id: 'mon-acc',
          ifDescr: 'GigabitEthernet0/2',
          metrics: { interface_ifOperStatus: 2 },
        },
      ],
    });

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-topo-link-l1-cross')).toBeTruthy();
    });
    expect(screen.getByTestId('status-topo-link-l1-status').textContent).toBe('down');
    expect(screen.getByTestId('status-topo-link-l1-source-traffic').textContent).toContain('↓');
    expect(screen.getByTestId('status-topo-status-core-1').textContent).toBe('normal');
  });

  it('marks a fully up link without a cross', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(linkedPayload);
    mockLinkedOverlay({
      items: [
        {
          instance_id: 'mon-core',
          ifDescr: 'GigabitEthernet0/1',
          metrics: { interface_ifOperStatus: 1, interface_ifHCInOctets: 8 },
        },
        {
          instance_id: 'mon-acc',
          ifDescr: 'GigabitEthernet0/2',
          metrics: { interface_ifOperStatus: 1, interface_ifHCOutOctets: 3 },
        },
      ],
    });

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-topo-link-l1-status').textContent).toBe('up');
    });
    expect(screen.queryByTestId('status-topo-link-l1-cross')).toBeNull();
  });

  it('does not invent traffic or a cross when the port name does not match', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(linkedPayload);
    mockLinkedOverlay({
      items: [{
        instance_id: 'mon-core',
        ifDescr: 'Eth1/1',
        metrics: { interface_ifOperStatus: 2 },
      }],
    });

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-topo-link-l1')).toBeTruthy();
    });
    expect(screen.queryByTestId('status-topo-link-l1-cross')).toBeNull();
    expect(screen.getByTestId('status-topo-link-l1-status').textContent).toBe('unknown');
    expect(screen.getByTestId('status-topo-link-l1-source-traffic').textContent).toBe('');

    fireEvent.mouseEnter(screen.getByTestId('status-topo-port-l1-source'));
    const popover = await screen.findByTestId('status-topo-port-popover');
    expect(popover.textContent).toContain('dashboard.networkTopoPortUnmatched');
  });

  it('hides always-on traffic when both checkboxes are cleared but still paints a down cross', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(linkedPayload);
    mockLinkedOverlay({
      items: [
        {
          instance_id: 'mon-core',
          ifDescr: 'GigabitEthernet0/1',
          metrics: { interface_ifOperStatus: 2, interface_ifHCInOctets: 8 },
        },
        {
          instance_id: 'mon-acc',
          ifDescr: 'GigabitEthernet0/2',
          metrics: { interface_ifOperStatus: 1 },
        },
      ],
    });

    render(
      <NetworkStatusTopology
        config={{
          networkStatusTopology: {
            ...widgetConfig.networkStatusTopology,
            linkTrafficDisplays: [],
          },
        }}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-topo-link-l1-cross')).toBeTruthy();
    });
    expect(screen.getByTestId('status-topo-link-l1-source-traffic').textContent).toBe('');
  });

  it('keeps node overlay and retries only interface runtime when that query fails', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(linkedPayload);
    mockLinkedOverlay({ interfaceFail: true });

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('status-topo-interface-error')).toBeTruthy();
    });
    expect(screen.queryByTestId('status-topo-overlay-error')).toBeNull();
    expect(screen.getByTestId('status-topo-status-core-1').textContent).toBe('normal');
    expect(screen.queryByTestId('status-topo-link-l1-cross')).toBeNull();

    overlayState.getSourceDataByApiId.mockImplementation((id: number) => {
      if (id === 31) {
        return Promise.resolve({
          data: {
            items: [
              { inst_uuid: 'core-1', model_id: 'switch', monitor_id: 'mon-core' },
              { inst_uuid: 'acc-1', model_id: 'switch', monitor_id: 'mon-acc' },
            ],
          },
          warnings: [],
        });
      }
      if (id === 33) {
        return Promise.resolve({ data: { items: [] }, warnings: [] });
      }
      return Promise.resolve(quietSummaries);
    });

    fireEvent.click(
      within(screen.getByTestId('status-topo-interface-error')).getByRole('button'),
    );
    await waitFor(() => {
      expect(overlayParamsFor(33).length).toBeGreaterThan(1);
    });
    expect(screen.getByTestId('status-topo-status-core-1').textContent).toBe('normal');
  });

  it('does not query interfaces when overlay mapping fails', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue(linkedPayload);
    overlayState.getSourceDataByApiId.mockRejectedValue(new Error('overlay down'));

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
    expect(screen.queryByTestId('status-topo-interface-error')).toBeNull();
    expect(overlayParamsFor(33)).toEqual([]);
    expect(screen.getByTestId('status-topo-status-core-1').textContent).toBe('unknown');
    expect(screen.queryByTestId('status-topo-link-l1-cross')).toBeNull();

    fireEvent.mouseEnter(screen.getByTestId('status-topo-port-l1-source'));
    const popover = await screen.findByTestId('status-topo-port-popover');
    expect(popover.textContent).toContain('dashboard.networkTopoUnmonitored');
  });

  it('still loads interface runtime in share mode', async () => {
    overlayState.shareMode = true;
    testState.getNetworkStatusTopology.mockResolvedValue(linkedPayload);
    mockLinkedOverlay({
      items: [
        {
          instance_id: 'mon-core',
          ifDescr: 'GigabitEthernet0/1',
          metrics: { interface_ifOperStatus: 1, interface_ifHCInOctets: 8 },
        },
        {
          instance_id: 'mon-acc',
          ifDescr: 'GigabitEthernet0/2',
          metrics: { interface_ifOperStatus: 1 },
        },
      ],
    });

    render(
      <NetworkStatusTopology
        config={widgetConfig}
        refreshKey="0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(overlayParamsFor(33)).toEqual([{ instance_ids: ['mon-core', 'mon-acc'] }]);
    });
    expect(screen.getByTestId('status-topo-link-l1-source-traffic').textContent).toContain('↓');
    expect(overlayState.getDataSourceBriefList).not.toHaveBeenCalled();
  });
});

