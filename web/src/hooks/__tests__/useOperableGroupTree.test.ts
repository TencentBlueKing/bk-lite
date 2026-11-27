import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useOperableGroupTree } from '@/hooks/useOperableGroupTree';

const mocks = vi.hoisted(() => ({
  pathname: '/cmdb/assetManage',
  roles: ['cmdb--module_admin'],
  groupTree: [{ id: '1', name: 'Home' }],
  moduleGroupTree: [{ id: '9', name: 'Foreign' }],
}));
vi.mock('next/navigation', () => ({ usePathname: () => mocks.pathname }));
vi.mock('@/context/userInfo', () => ({ useUserInfoContext: () => mocks }));
describe('current app operable org tree', () => {
  it('uses module tree only in the authorized app and falls back when empty', () => {
    const { result, rerender } = renderHook(() => useOperableGroupTree());
    expect(result.current).toBe(mocks.moduleGroupTree);
    mocks.pathname = '/system-manager/user'; rerender();
    expect(result.current).toBe(mocks.groupTree);
    mocks.pathname = '/monitor/event'; rerender();
    expect(result.current).toBe(mocks.groupTree);
    mocks.pathname = '/cmdb/assetManage'; mocks.moduleGroupTree = []; rerender();
    expect(result.current).toBe(mocks.groupTree);
  });
});
