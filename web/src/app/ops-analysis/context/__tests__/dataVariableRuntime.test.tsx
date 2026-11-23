// @vitest-environment jsdom

import React, { StrictMode } from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DataVariable } from '@/app/ops-analysis/utils/dataVariable';

const fetchState = vi.hoisted(() => ({
  getSourceDataByApiId: vi.fn(),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getSourceDataByApiId: (...args: unknown[]) => fetchState.getSourceDataByApiId(...args),
  }),
}));

import {
  DataVariableRuntimeProvider,
  useDataVariableRuntime,
} from '../dataVariableRuntime';

const variables: DataVariable[] = [{
  id: 'dv_region',
  name: 'region uuids',
  dataSourceId: 130,
  valueField: 'inst_uuids',
  params: {},
}];

const Probe = () => {
  const runtime = useDataVariableRuntime();
  return <div data-testid="ready">{String(Boolean(runtime?.ready))}</div>;
};

afterEach(() => {
  cleanup();
  fetchState.getSourceDataByApiId.mockReset();
});

describe('DataVariableRuntimeProvider', () => {
  it('does not restart when referencedValues is a new object with the same variable ids', async () => {
    let resolveFetch: (value: { data: unknown }) => void = () => undefined;
    fetchState.getSourceDataByApiId.mockImplementation(
      () => new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );

    const view = render(
      <DataVariableRuntimeProvider
        variables={variables}
        referencedValues={{ uuids: { dataVariableId: 'dv_region' } }}
        filterValues={{}}
      >
        <Probe />
      </DataVariableRuntimeProvider>,
    );

    await waitFor(() => {
      expect(fetchState.getSourceDataByApiId).toHaveBeenCalledTimes(1);
    });

    view.rerender(
      <DataVariableRuntimeProvider
        variables={variables}
        referencedValues={{ uuids: { dataVariableId: 'dv_region' } }}
        filterValues={{}}
      >
        <Probe />
      </DataVariableRuntimeProvider>,
    );
    view.rerender(
      <DataVariableRuntimeProvider
        variables={[...variables]}
        referencedValues={{ uuids: { dataVariableId: 'dv_region' } }}
        filterValues={{}}
      >
        <Probe />
      </DataVariableRuntimeProvider>,
    );

    expect(fetchState.getSourceDataByApiId).toHaveBeenCalledTimes(1);
    expect(view.getByTestId('ready').textContent).toBe('false');

    resolveFetch({ data: [] });
    await waitFor(() => {
      expect(view.getByTestId('ready').textContent).toBe('true');
    });
    expect(fetchState.getSourceDataByApiId).toHaveBeenCalledTimes(1);
  });

  it('reuses a ready parent column so a nested preview does not refetch', async () => {
    fetchState.getSourceDataByApiId.mockResolvedValue({ data: [] });

    const view = render(
      <DataVariableRuntimeProvider
        variables={variables}
        referencedValues={{ uuids: { dataVariableId: 'dv_region' } }}
        filterValues={{}}
      >
        <Probe />
      </DataVariableRuntimeProvider>,
    );

    await waitFor(() => {
      expect(view.getByTestId('ready').textContent).toBe('true');
    });
    expect(fetchState.getSourceDataByApiId).toHaveBeenCalledTimes(1);

    view.rerender(
      <DataVariableRuntimeProvider
        variables={variables}
        referencedValues={{ uuids: { dataVariableId: 'dv_region' } }}
        filterValues={{}}
      >
        <DataVariableRuntimeProvider
          variables={variables}
          referencedValues={{ uuids: { dataVariableId: 'dv_region' } }}
          filterValues={{}}
        >
          <Probe />
        </DataVariableRuntimeProvider>
      </DataVariableRuntimeProvider>,
    );

    await waitFor(() => {
      expect(view.getByTestId('ready').textContent).toBe('true');
    });
    expect(fetchState.getSourceDataByApiId).toHaveBeenCalledTimes(1);
  });

  it('refetches only the edited variable when another variable is unchanged', async () => {
    fetchState.getSourceDataByApiId.mockResolvedValue({ data: [{ inst_uuids: ['a'], id: 1 }] });
    const other: DataVariable = {
      id: 'dv_other',
      name: 'other',
      dataSourceId: 131,
      valueField: 'id',
      params: {},
    };
    const view = render(
      <DataVariableRuntimeProvider
        variables={[variables[0], other]}
        referencedValues={{
          uuids: { dataVariableId: 'dv_region' },
          ids: { dataVariableId: 'dv_other' },
        }}
        filterValues={{}}
      >
        <Probe />
      </DataVariableRuntimeProvider>,
    );
    await waitFor(() => {
      expect(view.getByTestId('ready').textContent).toBe('true');
    });
    expect(fetchState.getSourceDataByApiId).toHaveBeenCalledTimes(2);
    fetchState.getSourceDataByApiId.mockClear();

    view.rerender(
      <DataVariableRuntimeProvider
        variables={[{ ...variables[0], name: 'renamed' }, other]}
        referencedValues={{
          uuids: { dataVariableId: 'dv_region' },
          ids: { dataVariableId: 'dv_other' },
        }}
        filterValues={{}}
      >
        <Probe />
      </DataVariableRuntimeProvider>,
    );
    await waitFor(() => {
      expect(view.getByTestId('ready').textContent).toBe('true');
    });
    expect(fetchState.getSourceDataByApiId).not.toHaveBeenCalled();

    view.rerender(
      <DataVariableRuntimeProvider
        variables={[{ ...variables[0], params: { region: 'sh' } }, other]}
        referencedValues={{
          uuids: { dataVariableId: 'dv_region' },
          ids: { dataVariableId: 'dv_other' },
        }}
        filterValues={{}}
      >
        <Probe />
      </DataVariableRuntimeProvider>,
    );
    await waitFor(() => {
      expect(fetchState.getSourceDataByApiId).toHaveBeenCalledTimes(1);
    });
    expect(fetchState.getSourceDataByApiId.mock.calls[0]?.[0]).toBe(130);
    expect(view.getByTestId('ready').textContent).toBe('true');
  });

  it('aborts the old variable request on a real unmount and keeps the new one', async () => {
    const signals: AbortSignal[] = [];
    fetchState.getSourceDataByApiId.mockImplementation(
      (_id: number, _params: unknown, options?: { signal?: AbortSignal }) => new Promise((_resolve, reject) => {
        const signal = options?.signal;
        if (!signal) return;
        signals.push(signal);
        signal.addEventListener('abort', () => {
          reject(Object.assign(new Error('canceled'), { name: 'CanceledError', code: 'ERR_CANCELED' }));
        }, { once: true });
      }),
    );
    const tree = (id: string) => (
      <StrictMode>
        <div key={id}>
          <DataVariableRuntimeProvider
            variables={variables}
            referencedValues={{ uuids: { dataVariableId: 'dv_region' } }}
            filterValues={{}}
            scopeKey={id}
          >
            <Probe />
          </DataVariableRuntimeProvider>
        </div>
      </StrictMode>
    );
    const view = render(tree('a'));
    await waitFor(() => expect(signals.some((signal) => !signal.aborted)).toBe(true));
    const previous = signals.filter((signal) => !signal.aborted);
    view.rerender(tree('b'));
    await waitFor(() => expect(previous.every((signal) => signal.aborted)).toBe(true));
    expect(signals.some((signal) => !signal.aborted)).toBe(true);
  });
});
