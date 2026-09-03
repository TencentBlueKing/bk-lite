import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import JobHostSelectionModal, { HostItem } from '..';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/job/components/driver-badge', () => ({
  default: () => null,
}));

vi.mock('@/components/operate-form-modal', () => ({
  default: ({ children, onConfirm }: React.PropsWithChildren<{ onConfirm: () => void }>) => (
    <div>
      {children}
      <button type="button" onClick={onConfirm}>job.confirm</button>
    </div>
  ),
}));

vi.mock('@/components/selection-preview-layout', () => ({
  default: ({
    primary,
    items,
  }: {
    primary: React.ReactNode;
    items: Array<{ key: string; label: React.ReactNode }>;
  }) => (
    <div>
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
    pagination: { current: number; onChange: (page: number) => void };
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
        <button type="button" onClick={() => pagination.onChange(2)}>page-2</button>
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
    expect(screen.getByText('first-page-host')).toBeTruthy();

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
