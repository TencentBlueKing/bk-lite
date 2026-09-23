import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useTransferTasks } from '../useTransferTasks';

const list = vi.hoisted(() => vi.fn());
vi.mock('@/app/cmdb/api/transfer', () => ({ useTransferApi: () => ({ list, identity: 'user-a' }) }));
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks(); });

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
