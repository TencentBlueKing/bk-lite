import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const widgetState = vi.hoisted(() => ({
  status: 'ready' as 'unavailable' | 'loading' | 'ready',
  declared: true,
  loadWidget: async () => ({ default: () => null }),
}));

const lazyState = vi.hoisted(() => ({
  Widget: null as React.ComponentType<{
    monitorId?: string;
    nodeId?: string;
    instUuid?: string;
  }> | null,
  loadFailed: false,
  loadCalls: [] as boolean[],
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () =>
    new URLSearchParams(`inst_uuid=${INST_UUID}&model_id=host`),
}));

vi.mock('@/context/appCapabilities', async () => {
  const actual = await vi.importActual<typeof import('@/context/appCapabilities')>(
    '@/context/appCapabilities',
  );
  return {
    ...actual,
    useAppWidget: () => ({
      status: widgetState.status,
      declared: widgetState.declared,
      loadWidget: widgetState.loadWidget,
    }),
    useLazyAppWidget: ({ active }: { active: boolean }) => {
      lazyState.loadCalls.push(active);
      return { Widget: lazyState.Widget, loadFailed: lazyState.loadFailed };
    },
  };
});

vi.mock('@/app/cmdb/api', () => ({
  useInstanceApi: () => ({
    getInstanceDetail: async () => ({
      monitor_id: 'mon-1',
      node_id: 'node-1',
    }),
  }),
}));

import { CmdbPublicWidgetPage } from '../CmdbPublicWidgetPage';

afterEach(() => {
  cleanup();
  widgetState.status = 'ready';
  widgetState.declared = true;
  lazyState.Widget = null;
  lazyState.loadFailed = false;
  lazyState.loadCalls = [];
});

// 售卖门只由提供方模块的目录声明表达：未购提供方 → 探测不到该键 → declared 为 false。
// 宿主是 CMDB 这件事本身不构成额外的门，尤其不构成「已购运营分析」的门。
describe('CmdbPublicWidgetPage provider gate', () => {
  it('activates a monitor widget once monitor declared it', async () => {
    lazyState.Widget = function PublicMonitorWidget({
      monitorId,
    }: {
      monitorId?: string;
    }) {
      return <div>{`public-monitor:${monitorId}`}</div>;
    };
    render(
      <CmdbPublicWidgetPage
        widgetKey="monitor.monitorView"
        identifierProp="monitorId"
      />,
    );
    expect(await screen.findByText('public-monitor:mon-1')).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(true);
  });

  it('activates node status from the host instance node_id', async () => {
    lazyState.Widget = function PublicNodeWidget({ nodeId }: { nodeId?: string }) {
      return <div>{`public-node:${nodeId}`}</div>;
    };
    render(
      <CmdbPublicWidgetPage
        widgetKey="node.nodeStatus"
        identifierProp="nodeId"
      />,
    );
    expect(await screen.findByText('public-node:node-1')).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(true);
  });

  it('activates an ops-analysis widget on the same declaration rule as the others', async () => {
    lazyState.Widget = function PublicApplication3DWidget({
      instUuid,
    }: {
      instUuid?: string;
    }) {
      return <div>{`public-3d:${instUuid}`}</div>;
    };
    render(
      <CmdbPublicWidgetPage
        widgetKey="ops-analysis.application3D"
        identifierProp="instUuid"
      />,
    );
    expect(await screen.findByText(`public-3d:${INST_UUID}`)).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(true);
  });

  it('hides any widget the provider did not declare, ops-analysis included', async () => {
    widgetState.declared = false;
    for (const widgetKey of [
      'monitor.monitorView',
      'ops-analysis.application3D',
    ] as const) {
      render(
        <CmdbPublicWidgetPage
          widgetKey={widgetKey}
          identifierProp="instUuid"
        />,
      );
      expect(await screen.findByText('common.noData')).toBeTruthy();
      expect(lazyState.loadCalls.at(-1)).toBe(false);
      cleanup();
    }
  });
});
