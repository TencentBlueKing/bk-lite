import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import JobHostSelectionModal, { type HostItem, type JobHostSelectionModalProps } from '..';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/job/components/driver-badge', () => ({
  default: () => null,
}));

vi.mock('@/components/operate-form-modal', () => ({
  default: ({
    children,
    onConfirm,
    width,
  }: React.PropsWithChildren<{ onConfirm: () => void; width: number }>) => (
    <div data-testid="host-modal" data-width={width}>
      {children}
      <button type="button" onClick={onConfirm}>job.confirm</button>
    </div>
  ),
}));

vi.mock('@/components/selection-preview-layout', () => ({
  default: ({
    primary,
    primaryWidth,
    items,
  }: {
    primary: React.ReactNode;
    primaryWidth: number;
    items: Array<{ key: string; label: React.ReactNode }>;
  }) => (
    <div data-testid="selection-layout" data-primary-width={primaryWidth}>
      {primary}
      <ul>
        {items.map((item) => <li key={item.key}>{item.label}</li>)}
      </ul>
    </div>
  ),
}));

vi.mock('@/components/custom-table', () => ({
  default: ({
    dataSource,
    rowSelection,
    pagination,
  }: {
    dataSource: HostItem[];
    rowSelection: {
      selectedRowKeys: React.Key[];
      preserveSelectedRowKeys?: boolean;
      onChange: (keys: React.Key[]) => void;
    };
    pagination: {
      current: number;
      pageSize: number;
      onChange: (page: number, pageSize: number) => void;
    };
  }) => {
    const pageKeys = new Set(dataSource.map((host) => host.key));

    return (
      <div>
        {dataSource.map((host) => (
          <button
            key={host.key}
            type="button"
            onClick={() => {
              const retainedKeys = rowSelection.preserveSelectedRowKeys
                ? rowSelection.selectedRowKeys
                : rowSelection.selectedRowKeys.filter((key) => pageKeys.has(String(key)));
              rowSelection.onChange(Array.from(new Set([...retainedKeys, host.key])));
            }}
          >
            select-{host.key}
          </button>
        ))}
        <button type="button" onClick={() => pagination.onChange(2, pagination.pageSize)}>
          page-2
        </button>
      </div>
    );
  },
}));

afterEach(cleanup);

const hostsByPage: Record<number, HostItem[]> = {
  1: [{
    key: 'host-1',
    hostName: 'first-page-host',
    ipAddress: '10.0.0.1',
    cloudRegion: 'default',
    osType: 'Linux',
    currentDriver: 'SSH',
  }],
  2: [{
    key: 'host-2',
    hostName: 'second-page-host',
    ipAddress: '10.0.0.2',
    cloudRegion: 'default',
    osType: 'Linux',
    currentDriver: 'SSH',
  }],
};

describe('JobHostSelectionModal cross-page selection', () => {
  it('requests the IP filter once when Enter commits the search value', async () => {
    const user = userEvent.setup();
    const request = vi.fn<JobHostSelectionModalProps['fetchHosts']>(
      async () => ({ items: [], total: 0 }),
    );

    render(
      <JobHostSelectionModal
        open
        selectedKeys={[]}
        selectedHosts={[]}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        fetchHosts={request}
      />,
    );
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    request.mockClear();

    const filterInput = screen.getAllByRole('combobox')[1];
    await user.click(filterInput);
    await user.type(filterInput, '10{Enter}');

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    expect(request).toHaveBeenLastCalledWith(expect.objectContaining({
      filters: {
        ip: [{ lookup_expr: 'icontains', value: '10' }],
      },
    }));
  });

  it('does not refetch when the request callback identity changes while open', async () => {
    const request = vi.fn<JobHostSelectionModalProps['fetchHosts']>(
      async () => ({ items: [], total: 0 }),
    );
    const selectedKeys: string[] = [];
    const selectedHosts: HostItem[] = [];
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const renderModal = () => (
      <JobHostSelectionModal
        open
        selectedKeys={selectedKeys}
        selectedHosts={selectedHosts}
        onConfirm={onConfirm}
        onCancel={onCancel}
        fetchHosts={(params) => request(params)}
      />
    );

    const { rerender } = render(renderModal());
    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));

    rerender(renderModal());
    rerender(renderModal());

    await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
  });

  it('keeps hosts selected on earlier pages when another page is selected', async () => {
    const onConfirm = vi.fn();
    const fetchHosts = vi.fn(async ({ page }: { page: number }) => ({
      items: hostsByPage[page] ?? [],
      total: 21,
    }));

    render(
      <JobHostSelectionModal
        open
        selectedKeys={[]}
        selectedHosts={[]}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
        fetchHosts={fetchHosts}
      />,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'select-host-1' }));
    const firstSelectedLabel = screen.getByText('first-page-host (10.0.0.1)');
    expect(firstSelectedLabel.className).toContain('truncate');
    expect(screen.getByTestId('host-modal').getAttribute('data-width')).toBe('960');
    expect(screen.getByTestId('selection-layout').getAttribute('data-primary-width')).toBe('660');

    fireEvent.click(screen.getByRole('button', { name: 'page-2' }));
    fireEvent.click(await screen.findByRole('button', { name: 'select-host-2' }));

    fireEvent.click(screen.getByRole('button', { name: 'job.confirm' }));

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledWith(
        ['host-1', 'host-2'],
        [hostsByPage[1][0], hostsByPage[2][0]],
      );
    });
  });
});
