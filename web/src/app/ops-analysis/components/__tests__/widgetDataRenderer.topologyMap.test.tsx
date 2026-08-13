// @vitest-environment jsdom

import React, { useEffect } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

const testState = vi.hoisted(() => ({
  payload: null as unknown,
  renderer: vi.fn(),
  renderFailure: false,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key === 'dashboard.dataFormatMismatch'
      ? 'Data format mismatch'
      : key,
  }),
}));

vi.mock('@/app/ops-analysis/context/common', () => ({
  useOpsAnalysis: () => ({ canvasDataSourceLookupStatus: 'ready' }),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getSourceDataByApiId: vi.fn(),
    getDataSourceList: vi.fn(),
  }),
}));

vi.mock('@/app/ops-analysis/hooks/useParamInputOptions', () => ({
  useParamInputOptions: () => ({ status: 'idle', options: [] }),
}));

vi.mock('@/app/ops-analysis/utils/compareQuery', () => ({
  fetchCompareData: async () => ({
    currentData: testState.payload,
    baselineData: null,
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetRegistry', () => ({
  getWidgetComponent: (chartType?: string) => {
    if (chartType !== 'topologyMap') return null;
    return function FakeTopologyMap({
      rawData,
      onReady,
      onError,
    }: {
      rawData: unknown;
      onReady?: (hasData?: boolean) => void;
      onError?: (message: string) => void;
    }) {
      testState.renderer(rawData);
      const hasData = Boolean(
        rawData &&
          typeof rawData === 'object' &&
          Array.isArray((rawData as { nodes?: unknown[] }).nodes) &&
          (rawData as { nodes: unknown[] }).nodes.length,
      );
      useEffect(() => {
        if (testState.renderFailure) {
          onError?.('Topology render failed');
          return;
        }
        onReady?.(hasData);
      }, [hasData, onError, onReady]);
      return <div data-testid="topology-map-renderer" />;
    };
  },
}));

import WidgetWrapper from '../widgetDataRenderer';

const datasource: DatasourceItem = {
  id: 42,
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
  domain: '',
  updated_by_domain: '',
  name: 'Topology NATS',
  source_type: 'nats',
  desc: '',
  params: [],
  chart_type: ['topologyMap'],
  namespaces: [],
};

const renderWidget = (widgetId: string, onRenderStatus = vi.fn()) => {
  render(
    <WidgetWrapper
      dashboardId={`dashboard-${widgetId}`}
      widgetId={widgetId}
      chartType="topologyMap"
      config={{ dataSource: datasource.id }}
      dataSource={datasource}
      onRenderStatus={onRenderStatus}
    />,
  );
  return onRenderStatus;
};

afterEach(() => {
  cleanup();
  testState.renderer.mockClear();
  testState.renderFailure = false;
});

describe('DataSource → widgetDataRenderer → topologyMap focused integration', () => {
  it('passes a valid graph object unchanged to renderer and reports ready', async () => {
    testState.payload = {
      nodes: [{
        id: 'a', instance_id: 1, instance_name: 'A', model_name: 'Host',
        alert_count: 0,
      }],
      edges: [],
    };
    const onRenderStatus = renderWidget('valid');

    await waitFor(() => expect(screen.getByTestId('topology-map-renderer')).toBeTruthy());
    expect(testState.renderer).toHaveBeenCalledWith(testState.payload);
    await waitFor(() => expect(onRenderStatus).toHaveBeenCalledWith({
      widgetId: 'valid', status: 'ready',
    }));
  });

  it('reports a legal empty graph as empty instead of loading', async () => {
    testState.payload = { nodes: [], edges: [] };
    const onRenderStatus = renderWidget('empty');

    await waitFor(() => expect(onRenderStatus).toHaveBeenCalledWith({
      widgetId: 'empty', status: 'empty',
    }));
  });

  it('shows the existing format error, reports failed, and never enters renderer', async () => {
    testState.payload = {
      nodes: [],
      edges: [{ source: 'missing-a', target: 'missing-b' }],
    };
    const onRenderStatus = renderWidget('invalid');

    await waitFor(() => expect(screen.getByText('Data format mismatch')).toBeTruthy());
    expect(testState.renderer).not.toHaveBeenCalled();
    expect(onRenderStatus).toHaveBeenCalledWith({
      widgetId: 'invalid',
      status: 'failed',
      error: 'Data format mismatch',
    });
  });

  it('turns renderer errors into a failed terminal status', async () => {
    testState.payload = {
      nodes: [{
        id: 'a', instance_id: 1, instance_name: 'A', model_name: 'Host',
        alert_count: 0,
      }],
      edges: [],
    };
    testState.renderFailure = true;
    const onRenderStatus = renderWidget('render-error');

    await waitFor(() => expect(onRenderStatus).toHaveBeenCalledWith({
      widgetId: 'render-error',
      status: 'failed',
      error: 'Topology render failed',
    }));
  });
});
