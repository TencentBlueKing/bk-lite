import React from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import JobHostSelectionModalRuntime from '../jobHostSelectionModalRuntime';
import type { FetchHostsParams, JobHostSelectionModalProps } from '../host-selection-modal';

const mocks = vi.hoisted(() => ({
  getTargetList: vi.fn(),
  queryNodes: vi.fn(),
  captureProps: vi.fn(),
}));

vi.mock('@/app/job/api', () => ({
  default: () => ({
    getTargetList: mocks.getTargetList,
    queryNodes: mocks.queryNodes,
  }),
}));

vi.mock('@/app/job/components/host-selection-modal', () => ({
  default: (props: JobHostSelectionModalProps) => {
    mocks.captureProps(props);
    return null;
  },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('JobHostSelectionModalRuntime request cancellation contract', () => {
  it('forwards the modal AbortSignal to the node-manager HTTP request', async () => {
    mocks.queryNodes.mockResolvedValue({ data: { count: 0, items: [] } });

    render(
      <JobHostSelectionModalRuntime
        open
        selectedKeys={[]}
        selectedHosts={[]}
        source="node_manager"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    await waitFor(() => expect(mocks.captureProps).toHaveBeenCalled());
    const props = mocks.captureProps.mock.lastCall?.[0] as JobHostSelectionModalProps;
    const controller = new AbortController();
    const params: FetchHostsParams = {
      page: 1,
      pageSize: 20,
      filters: { keyword: [{ lookup_expr: 'icontains', value: 'OneDC_UICamA01' }] },
      source: 'node_manager',
      signal: controller.signal,
    };

    await props.fetchHosts(params);

    expect(mocks.queryNodes).toHaveBeenCalledWith(
      {
        page: 1,
        page_size: 20,
        keyword: 'OneDC_UICamA01',
        os: undefined,
      },
      { signal: controller.signal },
    );
  });
});
