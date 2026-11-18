import { renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useItsmApi } from './useItsmApi';
const client = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn(), isLoading: false }));
vi.mock('@/utils/request', () => ({ default: () => client }));
it('流程列表直接请求无尾斜杠的代理路径，避免 308 往返并保留分页权限', async () => {
  client.get.mockResolvedValueOnce({ items: [{ id: 1 }], count: 1, can_edit: false });
  const { result } = renderHook(() => useItsmApi());
  expect(await result.current.listWorkflows()).toEqual({ items: [{ id: 1 }], count: 1, can_edit: false });
  expect(client.get).toHaveBeenCalledExactlyOnceWith('/itsm/api/workflows', { params: { page: 1, page_size: 100 } });
});
