import { renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { useItsmApi, itsmRequestPath } from './useItsmApi';
const client = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn(), isLoading: false }));
vi.mock('@/utils/request', () => ({ default: () => client }));
beforeEach(() => { vi.clearAllMocks(); client.get.mockResolvedValue({ items: [], count: 0 }); });
it('查询和写入统一使用无重定向的 ITSM 代理路径，保留参数和请求体', async () => {
  const { result } = renderHook(() => useItsmApi());
  await result.current.getIntegration(7);
  await result.current.saveIntegration({ name: '甲' }, 7);
  await result.current.saveIntegration({ name: '乙' });
  await result.current.remove('/itsm/api/integrations/7/', { data: { reason: '测试' } });
  expect(client.get).toHaveBeenCalledWith('/itsm/api/integrations/7', undefined);
  expect(client.put).toHaveBeenCalledWith('/itsm/api/integrations/7', { name: '甲' }, undefined);
  expect(client.post).toHaveBeenCalledWith('/itsm/api/integrations', { name: '乙' }, undefined);
  expect(client.del).toHaveBeenCalledWith('/itsm/api/integrations/7', { data: { reason: '测试' } });
});
it('刷新重新读取数据，且回调不随组件重绘变化', async () => {
  const { result, rerender } = renderHook(() => useItsmApi());
  const getIntegration = result.current.getIntegration;
  await getIntegration(1); rerender(); await result.current.getIntegration(1);
  expect(result.current.getIntegration).toBe(getIntegration);
  expect(client.get).toHaveBeenCalledTimes(2);
});

it('查询值中的斜杠与外部 URL 保持原样', () => {
  expect(itsmRequestPath('/itsm/api/stages/?id=1')).toBe('/itsm/api/stages?id=1');
  expect(itsmRequestPath('/itsm/api/search?q=https://example.com/')).toBe('/itsm/api/search?q=https://example.com/');
  expect(itsmRequestPath('https://example.com/')).toBe('https://example.com/');
});
