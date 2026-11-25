import { describe, expect, it } from 'vitest';

import { buildSourceMenus } from '@/app/system-manager/components/application/menu/hooks/useMenuConfig';
import type { MenuItem } from '@/types/index';

const menu = (item: Partial<MenuItem> & Pick<MenuItem, 'name' | 'url'>): MenuItem => ({
  title: item.title || item.name,
  icon: '',
  operation: [],
  ...item,
});

describe('buildSourceMenus', () => {
  const menus = [
    menu({ name: 'credential', url: '/system-manager/credential', title: '凭据管理' }),
    menu({
      name: 'channel_list',
      url: '/system-manager/channel',
      title: '通知渠道',
      children: [
        menu({
          name: 'channel_setting',
          url: '/system-manager/channel/detail/settings',
          title: '设置',
          isNotMenuItem: true,
        }),
      ],
    }),
    menu({ name: 'workflow_entry', url: '/workflow', title: '入口', isNotMenuItem: true }),
    menu({
      name: 'user',
      url: '/system-manager/user',
      title: '用户',
      children: [
        menu({ name: 'user_group', url: '/system-manager/user/group', title: '组' }),
      ],
    }),
    menu({
      name: 'application_list',
      url: '/system-manager/application',
      title: '应用管理',
      hasDetail: true,
      children: [
        menu({ name: 'application_role', url: '/system-manager/application/manage/role', title: '角色' }),
      ],
    }),
  ];

  it('keeps visible leaves and pages whose children are only hidden details', () => {
    const source = buildSourceMenus(menus, 'system-manager');
    expect(source.map((item) => item.name)).toEqual([
      'credential',
      'channel_list',
      'user',
      'application_list',
    ]);
    expect(source[0].isDetailMode).toBe(true);
    expect(source[0].sourceHasDetail).toBe(false);
    expect(source[1].hiddenChildren?.[0]).toMatchObject({
      name: 'channel_setting',
      isNotMenuItem: true,
    });
    expect(source[1].sourceHasDetail).toBe(false);
    expect(source[2].isDetailMode).toBe(false);
    expect(source[2].children?.map((item) => item.name)).toEqual(['user_group']);
    expect(source[3].sourceHasDetail).toBe(true);
  });
});
