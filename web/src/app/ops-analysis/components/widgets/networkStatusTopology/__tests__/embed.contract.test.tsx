// @vitest-environment jsdom

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { buildNetworkStatusTopologyQuery } from '@/app/ops-analysis/api/networkStatusTopology';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const PEER_UUID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const testState = vi.hoisted(() => ({
  getNetworkStatusTopology: vi.fn(),
  lastToolbar: null as Record<string, unknown> | null,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/ops-analysis/context/shareMode', () => ({
  useShareMode: () => false,
}));

vi.mock('@/app/ops-analysis/context/common', () => ({
  useOpsAnalysis: () => ({
    dataSources: [
      { id: 31, rest_api: 'cmdb/get_monitor_ids_by_inst_uuids', is_build_in: true },
      { id: 32, rest_api: 'monitor/query_latest_active_alerts', is_build_in: true },
      { id: 33, rest_api: 'monitor/query_latest_interface_metrics', is_build_in: true },
    ],
  }),
  useOpsAnalysisOptional: () => ({
    dataSources: [
      { id: 31, rest_api: 'cmdb/get_monitor_ids_by_inst_uuids', is_build_in: true },
      { id: 32, rest_api: 'monitor/query_latest_active_alerts', is_build_in: true },
      { id: 33, rest_api: 'monitor/query_latest_interface_metrics', is_build_in: true },
    ],
  }),
}));

vi.mock('@/app/ops-analysis/components/widget-viewport', () => ({
  useWidgetViewport: () => ({ scale: 1 }),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getSourceDataByApiId: vi.fn(async () => ({ data: [] })),
    getDataSourceBriefList: vi.fn(async () => []),
  }),
}));

vi.mock('@/app/ops-analysis/api/networkStatusTopology', async () => {
  const actual = await vi.importActual<
    typeof import('@/app/ops-analysis/api/networkStatusTopology')
      >('@/app/ops-analysis/api/networkStatusTopology');
  return {
    ...actual,
    useNetworkStatusTopologyApi: () => ({
      getNetworkStatusTopology: (...args: unknown[]) =>
        testState.getNetworkStatusTopology(...args),
    }),
  };
});

vi.mock('@/app/cmdb/components/networkTopology', () => ({
  NetworkTopologyX6Canvas: ({
    data,
    toolbar,
  }: {
    data: {
      nodes?: Array<{ id: string }>;
      links?: Array<{ id?: string; source?: string; target?: string }>;
    };
    toolbar?: Record<string, unknown>;
  }) => {
    testState.lastToolbar = toolbar || null;
    return (
      <div data-testid="status-topo-canvas">
        {(data.nodes || []).map((node) => (
          <span key={node.id} data-testid={`status-topo-node-${node.id}`}>
            {node.id}
          </span>
        ))}
        {(data.links || []).map((link, index) => (
          <span
            key={link.id || `${link.source}-${link.target}-${index}`}
            data-testid={`status-topo-link-${link.id || index}`}
          >
            {`${link.source || ''}->${link.target || ''}`}
          </span>
        ))}
        <div data-testid="status-topo-toolbar-keys">
          {Object.keys(toolbar || {}).join(',')}
        </div>
      </div>
    );
  },
  layoutNetworkTopology: ({
    nodes,
    links,
  }: {
    nodes: unknown[];
    links?: unknown[];
  }) => ({ nodes, links: links || [] }),
}));

vi.mock('../statusTopologyGraph', () => ({
  STATUS_TOPOLOGY_NODE_SHAPE: 'topo-network-status-device-test',
  STATUS_TOPOLOGY_PALETTE_DARK: {},
  STATUS_TOPOLOGY_PALETTE_LIGHT: {},
  STATUS_TOPOLOGY_VISUAL: {},
  isStatusTopologyIconHoverTarget: () => false,
  isStatusTopologyBadgeTarget: () => false,
  getStatusTopologyPortHoverEnd: () => null,
  ensureStatusTopologyNodeRegistered: vi.fn(),
  buildStatusTopologyX6GraphData: ({
    nodes,
    links,
  }: {
    nodes: unknown[];
    links?: unknown[];
  }) => ({ nodes, edges: [], links: links || [] }),
}));

import NetworkStatusTopologyEmbed from '../embed';

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

afterEach(() => {
  testState.getNetworkStatusTopology.mockReset();
  testState.lastToolbar = null;
  cleanup();
});

const embedSource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../embed.tsx'),
  'utf8',
);

describe('network status topology embed one-hop contract', () => {
  it('builds a depth=1 query only for single-center embed', () => {
    expect(
      buildNetworkStatusTopologyQuery({
        instUuids: [INST_UUID],
        nodeLimit: 100,
        oneHop: true,
      }),
    ).toEqual({
      inst_uuids: [INST_UUID],
      node_limit: 100,
      depth: 1,
    });
    expect(
      buildNetworkStatusTopologyQuery({
        instUuids: [INST_UUID],
        nodeLimit: 100,
      }),
    ).toEqual({
      inst_uuids: [INST_UUID],
      node_limit: 100,
    });
  });

  it('requests one hop and renders the neighbor when the fixture has one', async () => {
    testState.getNetworkStatusTopology.mockResolvedValue({
      center_id: INST_UUID,
      nodes: [
        { id: INST_UUID, model_id: 'switch', name: 'core', hop: 0 },
        { id: PEER_UUID, model_id: 'switch', name: 'peer', hop: 1 },
      ],
      links: [
        {
          relationship_id: 'rel-1',
          source_device: INST_UUID,
          target_device: PEER_UUID,
        },
      ],
      truncated: false,
      node_limit: 100,
    });

    render(<NetworkStatusTopologyEmbed instUuid={INST_UUID} />);

    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledWith({
        inst_uuids: [INST_UUID],
        node_limit: 100,
        depth: 1,
      });
    });

    expect(screen.getByTestId(`status-topo-node-${INST_UUID}`)).toBeTruthy();
    expect(screen.getByTestId(`status-topo-node-${PEER_UUID}`)).toBeTruthy();
    expect(screen.getByTestId('status-topo-canvas').textContent).toContain(PEER_UUID);
    expect(screen.queryByText(/hop|depth|跳数|expandDepth/i)).toBeNull();
    expect(screen.getByTestId('status-topo-toolbar-keys').textContent).not.toMatch(
      /hop|depth|expandDepth/i,
    );
    expect(embedSource).toContain('oneHop: true');
    expect(embedSource).toContain('layoutEditable={false}');
  });
});
