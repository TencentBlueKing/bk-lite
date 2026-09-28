import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import TransferDrawer from '../TransferDrawer';
import type { TransferTask } from '@/app/cmdb/types/transfer';

const cancel = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/cmdb/api/transfer', () => ({ useTransferApi: () => ({ cancel }) }));
Object.defineProperty(window, 'matchMedia', { value: () => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() }), writable: true });

it('renders accepted jobs as queued and cancels through the API before refreshing', async () => {
  const refresh = vi.fn().mockResolvedValue(undefined);
  const task: TransferTask = {
    task_id: 'one', type: 'import', model_id: 'host', model_name: '主机', team_id: 1, filename: 'host.xlsx',
    status: 'queued', phase: 'queued', processed_rows: 0, total_rows: null, summary: {}, message: '',
    available_actions: ['cancel'], created_at: '2026-09-21T00:00:00Z', finished_at: null, expires_at: '2026-09-28T00:00:00Z',
  };
  render(<TransferDrawer open onClose={() => undefined} tasks={[task]} error="" loading={false} onRefresh={refresh} />);
  expect(screen.getByText('Transfer.status.queued')).toBeTruthy();
  expect(screen.queryByText('Transfer.status.succeeded')).toBeNull();
  expect(screen.queryByText('Transfer.download')).toBeNull();
  fireEvent.click(screen.getByText('Transfer.cancel'));
  await waitFor(() => expect(cancel).toHaveBeenCalledWith('one'));
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
});

it('shows failure stage, uncertainty and execution protection without a verification action', () => {
  const task: TransferTask = {
    task_id: 'failed-import', type: 'import', model_id: 'host', model_name: '主机', team_id: 1, filename: 'host.xlsx',
    status: 'failed', phase: 'writing_instances', processed_rows: 1, total_rows: 3,
    summary: { created: 1, updated: null }, message: '依赖服务请求超时', available_actions: [],
    created_at: '2026-09-28T00:00:00Z', finished_at: '2026-09-28T00:01:00Z', expires_at: '2026-10-05T00:00:00Z',
    failure: { stage: 'writing_instances', error_type: 'TimeoutError', result_uncertain: true, execution_pending: true },
  };
  render(<TransferDrawer open onClose={() => undefined} tasks={[task]} error="" loading={false} onRefresh={async () => undefined} />);
  expect(screen.getByText('Transfer.status.failed')).toBeTruthy();
  expect(screen.getByText(/Transfer.phase.writing_instances/)).toBeTruthy();
  expect(screen.getByText('依赖服务请求超时')).toBeTruthy();
  expect(screen.getByText(/Transfer.count.updated: Transfer.unknown/)).toBeTruthy();
  expect(screen.getByText('Transfer.partialWriteHint')).toBeTruthy();
  expect(screen.getByText('Transfer.executionPending')).toBeTruthy();
  expect(screen.queryByText('Transfer.status.interrupted')).toBeNull();
});
