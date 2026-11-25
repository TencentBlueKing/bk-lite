// @vitest-environment jsdom

import React, { useEffect } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DashboardRenderOpsAnalysisProvider,
  useOpsAnalysis,
} from '@/app/ops-analysis/context/common';
import { useCanvasResources } from '@/app/ops-analysis/hooks/useCanvasResources';
import { createTransportCancelError } from '@/utils/requestCancellation';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

const getDataSourceDetails = vi.hoisted(() => vi.fn());
const getNamespaceList = vi.hoisted(() => vi.fn());

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceDetails,
    getDataSourceList: vi.fn(),
  }),
}));

vi.mock('@/app/ops-analysis/api/namespace', () => ({
  useNamespaceApi: () => ({ getNamespaceList }),
}));

const source = (id: number, namespaces: number[]): DatasourceItem => ({
  id,
  name: `ds-${id}`,
  namespaces,
} as DatasourceItem);

const NamespaceProbe = ({ ids }: { ids: number[] }) => {
  const { syncCanvasResources } = useCanvasResources();
  const { namespaceList } = useOpsAnalysis();
  const key = ids.join(',');
  useEffect(() => {
    void syncCanvasResources({
      source: ids,
      getDataSourceIds: (value) => value,
      getNamespaceIds: (_value, rows) => new Set(rows.flatMap((row) => row.namespaces ?? [])),
    });
  }, [ids, key, syncCanvasResources]);
  const label = namespaceList.map((item) => item.id).join(',') || 'empty';
  return <span data-testid="namespaces">{label}</span>;
};

const Harness = ({ ids }: { ids: number[] }) => (
  <DashboardRenderOpsAnalysisProvider>
    <NamespaceProbe ids={ids} />
  </DashboardRenderOpsAnalysisProvider>
);

afterEach(() => {
  cleanup();
  getDataSourceDetails.mockReset();
  getNamespaceList.mockReset();
});

describe('canvas lookup stale results', () => {
  it('does not let a cancelled lookup clear namespaces loaded by the newer canvas', async () => {
    getNamespaceList.mockImplementation(async (params: { ids?: string }) => (
      [{ id: Number(params.ids), name: 'ns' }]
    ));
    getDataSourceDetails.mockImplementation((ids: number[], signal?: AbortSignal) => {
      if (ids[0] === 11) {
        return new Promise((_resolve, reject) => {
          signal?.addEventListener('abort', () => {
            setTimeout(() => reject(createTransportCancelError()), 30);
          }, { once: true });
        });
      }
      return Promise.resolve([source(ids[0], [5])]);
    });

    const view = render(<Harness ids={[11]} />);
    view.rerender(<Harness ids={[22]} />);

    await waitFor(() => expect(screen.getByTestId('namespaces').textContent).toBe('5'));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByTestId('namespaces').textContent).toBe('5');
  });

  it('keeps the newest canvas across A then B then A when older lookups cancel late', async () => {
    const pending: Array<{
      id: number;
      resolve: (rows: DatasourceItem[]) => void;
    }> = [];
    getNamespaceList.mockImplementation(async (params: { ids?: string }) => (
      [{ id: Number(params.ids), name: 'ns' }]
    ));
    getDataSourceDetails.mockImplementation((ids: number[], signal?: AbortSignal) => new Promise((resolve, reject) => {
      pending.push({ id: ids[0], resolve });
      signal?.addEventListener('abort', () => {
        setTimeout(() => reject(createTransportCancelError()), 20);
      }, { once: true });
    }));

    const view = render(<Harness ids={[11]} />);
    await waitFor(() => expect(pending).toHaveLength(1));
    view.rerender(<Harness ids={[22]} />);
    await waitFor(() => expect(pending).toHaveLength(2));
    pending[1].resolve([source(22, [8])]);
    await waitFor(() => expect(screen.getByTestId('namespaces').textContent).toBe('8'));

    view.rerender(<Harness ids={[11]} />);
    await waitFor(() => expect(pending).toHaveLength(3));
    pending[2].resolve([source(11, [5])]);
    await waitFor(() => expect(screen.getByTestId('namespaces').textContent).toBe('5'));
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(screen.getByTestId('namespaces').textContent).toBe('5');
  });

  it('still clears namespaces when the current canvas has no data sources', async () => {
    getNamespaceList.mockResolvedValue([{ id: 5, name: 'ns' }]);
    getDataSourceDetails.mockResolvedValue([source(22, [5])]);
    const view = render(<Harness ids={[22]} />);
    await waitFor(() => expect(screen.getByTestId('namespaces').textContent).toBe('5'));
    view.rerender(<Harness ids={[]} />);
    await waitFor(() => expect(screen.getByTestId('namespaces').textContent).toBe('empty'));
  });

  it('returns an empty list for a current lookup whose detail response is empty', async () => {
    getDataSourceDetails.mockResolvedValue([]);
    const seen: Array<number | 'cancelled'> = [];
    const Probe = () => {
      const { loadCanvasDataSources } = useOpsAnalysis();
      useEffect(() => {
        void loadCanvasDataSources([22]).then((rows) => {
          seen.push(rows == null ? 'cancelled' : rows.length);
        });
      }, [loadCanvasDataSources]);
      return null;
    };
    render(
      <DashboardRenderOpsAnalysisProvider>
        <Probe />
      </DashboardRenderOpsAnalysisProvider>,
    );
    await waitFor(() => expect(seen).toEqual([0]));
  });
});
