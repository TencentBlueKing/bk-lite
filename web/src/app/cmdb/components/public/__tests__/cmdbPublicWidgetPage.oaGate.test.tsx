import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const clientState = vi.hoisted(() => ({
  clientData: [] as Array<{ name: string }>,
}));

const widgetState = vi.hoisted(() => ({
  status: 'ready' as 'unavailable' | 'loading' | 'ready',
  declared: true,
  loadWidget: async () => ({ default: () => null }),
}));

const lazyState = vi.hoisted(() => ({
  Widget: null as React.ComponentType<{
    monitorId?: string;
    nodeId?: string;
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

vi.mock('@/context/client', () => ({
  useClientData: () => ({
    clientData: clientState.clientData,
    loading: false,
  }),
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
  clientState.clientData = [];
  widgetState.status = 'ready';
  widgetState.declared = true;
  lazyState.Widget = null;
  lazyState.loadFailed = false;
  lazyState.loadCalls = [];
});

describe('CmdbPublicWidgetPage ops-analysis gate', () => {
  it('does not activate a monitor widget when ops-analysis is not sold', async () => {
    clientState.clientData = [{ name: 'monitor' }, { name: 'cmdb' }];
    render(
      <CmdbPublicWidgetPage
        widgetKey="monitor.monitorView"
        identifierProp="monitorId"
      />,
    );
    expect(await screen.findByText('common.noData')).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(false);
  });

  it('activates a monitor widget when ops-analysis is sold', async () => {
    clientState.clientData = [
      { name: 'monitor' },
      { name: 'cmdb' },
      { name: 'ops-analysis' },
    ];
    lazyState.Widget = function PublicMonitorWidget({
      monitorId,
    }: {
      monitorId: string;
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

  it('does not activate node status when ops-analysis is not sold', async () => {
    clientState.clientData = [{ name: 'node' }, { name: 'cmdb' }];
    render(
      <CmdbPublicWidgetPage
        widgetKey="node.nodeStatus"
        identifierProp="nodeId"
      />,
    );
    expect(await screen.findByText('common.noData')).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(false);
  });

  it('activates node status from the host instance node_id when ops-analysis is sold', async () => {
    clientState.clientData = [
      { name: 'node' },
      { name: 'cmdb' },
      { name: 'ops-analysis' },
    ];
    lazyState.Widget = function PublicNodeWidget({
      nodeId,
    }: {
      nodeId: string;
    }) {
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
});
