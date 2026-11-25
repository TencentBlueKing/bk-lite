// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const updateCustomMenu = vi.fn();

vi.mock('antd', () => ({
  message: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/app/system-manager/api/application', () => ({
  useRoleApi: () => ({ updateCustomMenu }),
}));

vi.mock('@/context/permissions', () => ({
  invalidateAppMenus: vi.fn(),
}));

import { message } from 'antd';
import { useMenuSave } from '@/app/system-manager/components/application/menu/hooks/useMenuConfigPage';
import type { MixedItem } from '@/app/system-manager/components/application/menu/hooks/useMenuConfig';

const t = (key: string) => key;

const emptyDirectory: MixedItem = {
  type: 'group',
  id: 'folder',
  data: { id: 'folder', name: '目录', icon: 'folder', children: [] },
};

const searchPage: MixedItem = {
  type: 'page',
  id: 'search',
  data: {
    name: 'search',
    display_name: '搜索',
    url: '/cmdb/search',
    icon: 'search',
    type: 'page',
  },
};

describe('useMenuSave', () => {
  beforeEach(() => {
    updateCustomMenu.mockReset();
    vi.mocked(message.error).mockClear();
  });

  it('does not save a menu that only contains empty directories', async () => {
    const { result } = renderHook(() => useMenuSave('1', 'cmdb', '自定义', [emptyDirectory], t));

    await act(async () => {
      await result.current.handleSaveMenu();
    });

    expect(updateCustomMenu).not.toHaveBeenCalled();
    expect(message.error).toHaveBeenCalledWith('system.menu.menuItemsRequired');
  });

  it('saves a menu that contains a real page', async () => {
    updateCustomMenu.mockResolvedValue({});
    const { result } = renderHook(() => useMenuSave('1', 'cmdb', '自定义', [searchPage], t));

    await act(async () => {
      await result.current.handleSaveMenu();
    });

    expect(updateCustomMenu).toHaveBeenCalledWith({
      id: '1',
      app: 'cmdb',
      display_name: '自定义',
      menus: [{ title: '搜索', name: 'search', url: '/cmdb/search', icon: 'search' }],
    });
  });
});
