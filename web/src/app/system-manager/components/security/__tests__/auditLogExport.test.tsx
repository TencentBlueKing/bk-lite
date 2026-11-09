import React, { act } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TableRowSelection } from 'antd/es/table/interface';

import OperationLogs from '../operationLogs';
import UserLoginLogs from '../loginLogs';

const { getOperationLogs, exportOperationLogs, getUserLoginLogs, exportUserLoginLogs } = vi.hoisted(() => ({
  getOperationLogs: vi.fn().mockResolvedValue({ items: [], count: 0 }),
  exportOperationLogs: vi.fn().mockResolvedValue(new Blob(['operation'])),
  getUserLoginLogs: vi.fn().mockResolvedValue({ items: [], count: 0 }),
  exportUserLoginLogs: vi.fn().mockResolvedValue(new Blob(['login'])),
}));

let operationSelection: TableRowSelection<unknown> | undefined;
let loginSelection: TableRowSelection<unknown> | undefined;

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/hooks/useLocalizedTime', () => ({
  useLocalizedTime: () => ({ convertToLocalizedTime: (value: string) => value }),
}));

vi.mock('@/context/client', () => ({
  useClientData: () => ({ clientData: [] }),
}));

vi.mock('@/app/system-manager/api/security', () => ({
  useSecurityApi: () => ({
    getOperationLogs,
    exportOperationLogs,
    getUserLoginLogs,
    exportUserLoginLogs,
  }),
}));

vi.mock('@/components/time-selector', () => ({
  default: React.forwardRef(function TimeSelectorMock() {
    return <div>time-selector</div>;
  }),
}));

vi.mock('@/components/custom-table', () => ({
  default: (props: { rowSelection?: TableRowSelection<unknown>; columns?: Array<{ key?: string }> }) => {
    if (props.columns?.some((column) => column.key === 'detail')) {
      operationSelection = props.rowSelection;
    } else {
      loginSelection = props.rowSelection;
    }
    return <div>audit-table</div>;
  },
}));

vi.mock('react-diff-viewer-continued', () => ({
  default: () => null,
}));

beforeEach(() => {
  getOperationLogs.mockResolvedValue({ items: [], count: 0 });
  exportOperationLogs.mockResolvedValue(new Blob(['operation']));
  getUserLoginLogs.mockResolvedValue({ items: [], count: 0 });
  exportUserLoginLogs.mockResolvedValue(new Blob(['login']));
  window.URL.createObjectURL = vi.fn(() => 'blob:audit-log');
  window.URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  operationSelection = undefined;
  loginSelection = undefined;
  getOperationLogs.mockReset();
  exportOperationLogs.mockReset();
  getUserLoginLogs.mockReset();
  exportUserLoginLogs.mockReset();
});

describe('OperationLogs export', () => {
  it('exports current filters without pagination, and selected ids when rows are chosen', async () => {
    render(<OperationLogs />);
    const exportButton = await screen.findByRole('button', { name: /common\.export/ });
    expect((exportButton as HTMLButtonElement).disabled).toBe(false);

    fireEvent.change(screen.getByPlaceholderText('system.security.operatorPlaceholder'), {
      target: { value: 'alice' },
    });
    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(exportOperationLogs).toHaveBeenCalledWith({ username: 'alice' });
    });
    const filterPayload = exportOperationLogs.mock.calls[0][0];
    expect(filterPayload.page).toBeUndefined();
    expect(filterPayload.page_size).toBeUndefined();

    await act(async () => {
      operationSelection?.onChange?.([11, 12], [], { type: 'all' });
    });
    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(exportOperationLogs).toHaveBeenLastCalledWith({ selected_ids: [11, 12] });
    });
    expect(window.URL.createObjectURL).toHaveBeenCalled();
  });
});

describe('UserLoginLogs export', () => {
  it('queries username and source_ip directly and exports like the OpenAPI page', async () => {
    render(<UserLoginLogs />);
    const exportButton = await screen.findByRole('button', { name: /common\.export/ });
    expect((exportButton as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText('system.security.exportCsv')).toBeNull();

    fireEvent.change(screen.getByPlaceholderText('system.user.table.username'), {
      target: { value: 'bob' },
    });
    fireEvent.change(screen.getByPlaceholderText('system.security.sourceIpPlaceholder'), {
      target: { value: '10.1.1.1' },
    });
    fireEvent.click(screen.getByRole('button', { name: /common\.search/ }));

    await waitFor(() => {
      const params = getUserLoginLogs.mock.calls.at(-1)?.[0];
      expect(params.username).toBe('bob');
      expect(params.source_ip).toBe('10.1.1.1');
      expect(params.username__icontains).toBeUndefined();
      expect(params.source_ip__icontains).toBeUndefined();
    });

    fireEvent.click(exportButton);
    await waitFor(() => {
      expect(exportUserLoginLogs).toHaveBeenCalled();
    });
    const filterPayload = exportUserLoginLogs.mock.calls[0][0];
    expect(filterPayload.username).toBe('bob');
    expect(filterPayload.source_ip).toBe('10.1.1.1');
    expect(filterPayload.page).toBeUndefined();
    expect(filterPayload.page_size).toBeUndefined();
    expect(filterPayload.login_time_start).toEqual(expect.any(String));
    expect(filterPayload.login_time_end).toEqual(expect.any(String));

    await act(async () => {
      loginSelection?.onChange?.([4], [], { type: 'single' });
    });
    fireEvent.click(exportButton);
    await waitFor(() => {
      expect(exportUserLoginLogs).toHaveBeenLastCalledWith({ selected_ids: [4] });
    });
  });
});
