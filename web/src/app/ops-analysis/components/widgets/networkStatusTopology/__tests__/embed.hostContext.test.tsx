// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const testState = vi.hoisted(() => ({
  getNetworkStatusTopology: vi.fn(async () => ({ nodes: [], links: [] })),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/ops-analysis/context/shareMode', () => ({
  useShareMode: () => false,
}));

vi.mock('@/app/ops-analysis/context/common', () => ({
  useOpsAnalysis: () => ({ dataSources: [] }),
  useOpsAnalysisOptional: () => ({ dataSources: [] }),
}));

vi.mock('@/app/ops-analysis/components/widget-viewport', () => ({
  useWidgetViewport: () => ({ scale: 1 }),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getSourceDataByApiId: vi.fn(),
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
  NetworkTopologyX6Canvas: () => <div data-testid="status-topo-canvas" />,
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
  testState.getNetworkStatusTopology.mockClear();
  cleanup();
});

describe('network status topology embed host context', () => {
  it('renders in a CMDB host without OpsAnalysisProvider', async () => {
    expect(() =>
      render(<NetworkStatusTopologyEmbed instUuid={INST_UUID} />),
    ).not.toThrow();
    await waitFor(() => {
      expect(testState.getNetworkStatusTopology).toHaveBeenCalledWith({
        inst_uuids: [INST_UUID],
        node_limit: 100,
        depth: 1,
      });
    });
  });
});
