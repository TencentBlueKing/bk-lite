// @vitest-environment jsdom

import React, { useEffect } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DashboardRenderOpsAnalysisProvider,
  useOpsAnalysis,
} from '@/app/ops-analysis/context/common';

const getDataSourceDetails = vi.hoisted(() => vi.fn());

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceDetails,
    getDataSourceList: vi.fn(),
  }),
}));

vi.mock('@/app/ops-analysis/api/namespace', () => ({
  useNamespaceApi: () => ({
    getNamespaceList: vi.fn(),
  }),
}));

const Probe = ({ ids }: { ids: number[] }) => {
  const { loadCanvasDataSources, canvasDataSourceLookupStatus } = useOpsAnalysis();
  useEffect(() => {
    void loadCanvasDataSources(ids);
  }, [ids, loadCanvasDataSources]);
  return <span>{canvasDataSourceLookupStatus}</span>;
};

afterEach(() => {
  cleanup();
  getDataSourceDetails.mockReset();
});

describe('canvas data source detail lookup', () => {
  it('aborts the detail request superseded by the next canvas and on provider unmount', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    getDataSourceDetails.mockImplementation(() => new Promise(() => undefined));
    const view = render(
      <DashboardRenderOpsAnalysisProvider>
        <Probe ids={[11]} />
      </DashboardRenderOpsAnalysisProvider>,
    );
    await vi.waitFor(() => expect(getDataSourceDetails).toHaveBeenCalledTimes(1));
    const first = getDataSourceDetails.mock.calls[0]?.[1] as AbortSignal;
    expect(first.aborted).toBe(false);

    view.rerender(
      <DashboardRenderOpsAnalysisProvider>
        <Probe ids={[22]} />
      </DashboardRenderOpsAnalysisProvider>,
    );
    await vi.waitFor(() => expect(getDataSourceDetails).toHaveBeenCalledTimes(2));
    const second = getDataSourceDetails.mock.calls[1]?.[1] as AbortSignal;
    expect(getDataSourceDetails.mock.calls[1]?.[0]).toEqual([22]);
    expect(first.aborted).toBe(true);
    expect(second.aborted).toBe(false);
    expect(screen.getByText('loading')).toBeTruthy();
    expect(errorSpy).not.toHaveBeenCalled();

    view.unmount();
    expect(second.aborted).toBe(true);
    errorSpy.mockRestore();
  });
});
