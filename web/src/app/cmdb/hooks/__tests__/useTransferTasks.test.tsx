import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useTransferTasks } from '../useTransferTasks';

const list = vi.hoisted(() => vi.fn());
vi.mock('@/app/cmdb/api/transfer', () => ({ useTransferApi: () => ({ list, identity: 'user-a' }) }));
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

it('allows consecutive submissions and keeps history alongside active tasks', async () => {
  const task = { task_id: 'new', type: 'export', model_id: 'host', model_name: '主机', team_id: 1, filename: '',
    status: 'queued', phase: 'queued', processed_rows: 0, total_rows: null, summary: {}, message: '', available_actions: [],
    created_at: '', finished_at: null, expires_at: '' } as const;
  const history = Array.from({ length: 5 }, (_, index) => ({ ...task, task_id: `history-${index}`, status: 'succeeded' }));
  list.mockResolvedValueOnce({ items: history, can_submit: true, limits: { active: 5 } });
  const { result } = renderHook(() => useTransferTasks(true, () => undefined));
  await act(async () => { await Promise.resolve(); });
  list.mockImplementation(() => new Promise(() => undefined));
  act(() => result.current.submitted({ ...task, available_actions: [] }));
  expect(result.current.tasks).toHaveLength(6);
  expect(result.current.canSubmit).toBe(true);
  for (let index = 0; index < 4; index++) {
    act(() => result.current.submitted({ ...task, task_id: `queued-${index}`, available_actions: [] }));
  }
  expect(result.current.tasks).toHaveLength(10);
  expect(result.current.canSubmit).toBe(false);
});

it('restores pending jobs and stops polling once they finish', async () => {
  vi.useFakeTimers();
  list.mockResolvedValueOnce({ items: [{ task_id: 'one', type: 'import', model_id: 'host', status: 'queued' }], can_submit: false })
    .mockResolvedValue({ items: [{ task_id: 'one', type: 'import', model_id: 'host', status: 'succeeded' }], can_submit: true });
  const completed = vi.fn();
  const { result, unmount } = renderHook(() => useTransferTasks(true, completed));
  await act(async () => { await Promise.resolve(); });
  expect(result.current.tasks[0].status).toBe('queued');
  expect(completed).not.toHaveBeenCalled();
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(completed).toHaveBeenCalledTimes(1);
  await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
  expect(list).toHaveBeenCalledTimes(2);
  unmount();
});

it('pauses on hidden documents and inactive CMDB pages, then refreshes on return', async () => {
  vi.useFakeTimers();
  list.mockResolvedValue({ items: [{ task_id: 'one', type: 'export', status: 'running' }], can_submit: false });
  const { rerender, unmount } = renderHook(({ enabled }) => useTransferTasks(false, () => undefined, enabled), { initialProps: { enabled: true } });
  await act(async () => { await Promise.resolve(); });
  Object.defineProperty(document, 'hidden', { configurable: true, value: true });
  act(() => { document.dispatchEvent(new Event('visibilitychange')); });
  await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
  expect(list).toHaveBeenCalledTimes(1);
  Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  await act(async () => { document.dispatchEvent(new Event('visibilitychange')); await Promise.resolve(); });
  expect(list).toHaveBeenCalledTimes(2);
  rerender({ enabled: false });
  await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
  expect(list).toHaveBeenCalledTimes(2);
  rerender({ enabled: true });
  await act(async () => { await Promise.resolve(); });
  expect(list).toHaveBeenCalledTimes(3);
  unmount();
});

it('keeps polling a failed task until its previous execution has stopped', async () => {
  vi.useFakeTimers();
  const failed = { task_id: 'one', type: 'import', status: 'failed' };
  list.mockResolvedValueOnce({ items: [{ ...failed, failure: { execution_pending: true } }], can_submit: true })
    .mockResolvedValue({ items: [{ ...failed, failure: { execution_pending: false } }], can_submit: true });
  const completed = vi.fn();
  const { result, unmount } = renderHook(() => useTransferTasks(true, completed));
  await act(async () => { await Promise.resolve(); });
  expect(result.current.canSubmit).toBe(true);
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(list).toHaveBeenCalledTimes(2);
  expect(result.current.tasks[0].failure?.execution_pending).toBe(false);
  await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
  expect(list).toHaveBeenCalledTimes(2);
  expect(completed).not.toHaveBeenCalled();
  unmount();
});
