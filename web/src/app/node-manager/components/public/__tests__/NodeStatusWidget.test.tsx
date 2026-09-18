import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

const apis = vi.hoisted(() => ({
  getNodeList: vi.fn(),
}));

const mockTranslate = (key: string, defaultVal?: string) => defaultVal || key;

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: mockTranslate,
  }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({
    convertToLocalizedTime: (time: string) => `formatted-${time}`,
  }),
}));

vi.mock('@/app/node-manager/api/useNodeApi', () => ({
  default: () => ({
    getNodeList: async (...args: unknown[]) => apis.getNodeList(...args),
  }),
}));

import NodeStatusWidget from '../NodeStatusWidget';

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
  cleanup();
  vi.clearAllMocks();
});

describe('NodeStatusWidget success state', () => {
  it('renders rich header, sidecar card, collectors summary, and collector table on success', async () => {
    apis.getNodeList.mockResolvedValueOnce({
      items: [
        {
          id: 'node-test-101',
          name: 'prod-api-server-01',
          ip: '192.168.1.10',
          operating_system: 'linux',
          cpu_architecture: 'x86_64',
          install_method: 'auto',
          updated_at: '2026-09-16T10:00:00Z',
          active: true,
          status: {
            status: 0,
            message: 'Heartbeat healthy',
            collectors: [
              {
                collector_id: 'telegraf',
                collector_name: 'Telegraf Agent',
                status: 0,
                message: 'Running',
              },
              {
                collector_id: 'custom_monitor',
                collector_name: 'Custom Plugin',
                status: 2,
                message: 'Connection refused on port 9100',
              },
            ],
          },
          versions: [
            {
              component_type: 'controller',
              version: '1.4.2',
              latest_version: '1.5.0',
              upgradeable: true,
            },
            {
              component_type: 'collector',
              component_id: 'telegraf',
              version: '1.28.0',
              latest_version: '1.28.0',
              upgradeable: false,
            },
            {
              component_type: 'collector',
              component_id: 'custom_monitor',
              version: '0.9.1',
              latest_version: '1.0.0',
              upgradeable: true,
            },
          ],
        },
      ],
    });

    render(<NodeStatusWidget nodeId="node-test-101" />);

    expect(apis.getNodeList).toHaveBeenCalled();

    await waitFor(() => {
      // 头部主机基础信息
      expect(screen.getByText('prod-api-server-01')).toBeTruthy();
      expect(screen.getByText('192.168.1.10')).toBeTruthy();
      expect(screen.getByText('Linux')).toBeTruthy();
      expect(screen.getByText('x86_64')).toBeTruthy();
      expect(screen.getByText('formatted-2026-09-16T10:00:00Z')).toBeTruthy();

      // Sidecar 控制器卡片
      expect(screen.getByText('v1.4.2')).toBeTruthy();
      expect(screen.getByText('Heartbeat healthy')).toBeTruthy();

      // 托管组件卡片（文案为组件总数，不是节点总数）
      expect(
        screen.getByText(/组件总数: 2|node-manager.cloudregion.node.collectorTotal: 2/),
      ).toBeTruthy();
      expect(screen.queryByText(/节点总数/)).toBeNull();

      // 采集器列表表格
      expect(screen.getByText('Telegraf Agent')).toBeTruthy();
      expect(screen.getByText('telegraf')).toBeTruthy();
      expect(screen.getByText('1.28.0')).toBeTruthy();

      expect(screen.getByText('Custom Plugin')).toBeTruthy();
      expect(screen.getByText('custom_monitor')).toBeTruthy();
      expect(screen.getByText('0.9.1')).toBeTruthy();
      expect(screen.getByText('Connection refused on port 9100')).toBeTruthy();
    });
  });

  it('renders offline warning and empty collector message gracefully', async () => {
    apis.getNodeList.mockResolvedValueOnce({
      items: [
        {
          id: 'node-test-102',
          name: 'offline-node-02',
          ip: '192.168.1.11',
          active: false,
          status: {
            message: 'Heartbeat timeout',
            collectors: [],
          },
        },
      ],
    });

    render(<NodeStatusWidget nodeId="node-test-102" />);

    await waitFor(() => {
      expect(screen.getByText('offline-node-02')).toBeTruthy();
      expect(screen.getByText('Heartbeat timeout')).toBeTruthy();
      expect(screen.getByText('common.noData')).toBeTruthy();
    });
  });

  it('hides stale healthy heartbeat message when node is offline', async () => {
    apis.getNodeList.mockResolvedValueOnce({
      items: [
        {
          id: 'node-test-103',
          name: 'offline-node-03',
          ip: '192.168.1.12',
          active: false,
          status: {
            // 上次心跳存留的 healthy 摘要
            message: 'Heartbeat healthy · collectors reporting',
            collectors: [],
          },
        },
      ],
    });

    render(<NodeStatusWidget nodeId="node-test-103" />);

    await waitFor(() => {
      expect(screen.getByText('offline-node-03')).toBeTruthy();
      // 离线时过滤掉暗示健康的过期文案，不得与离线态打架
      expect(
        screen.queryByText('Heartbeat healthy · collectors reporting'),
      ).toBeNull();
    });
  });

  it('renders empty state and retry button on load failure', async () => {
    apis.getNodeList.mockResolvedValueOnce({
      items: [],
    });

    render(<NodeStatusWidget nodeId="node-test-missing" />);

    await waitFor(() => {
      expect(
        screen.getByText('node-manager.cloudregion.node.publicWidgetNotFound'),
      ).toBeTruthy();
      expect(screen.getByText('common.retry')).toBeTruthy();
    });
  });
});
