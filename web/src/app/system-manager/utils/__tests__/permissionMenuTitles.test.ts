import { describe, expect, it } from 'vitest';
import { localizePermissionMenus, type AppMenuTitleNode } from '@/app/system-manager/utils/permissionMenuTitles';
import type { Menu } from '@/app/system-manager/types/application';

const appMenus: AppMenuTitleNode[] = [
  {
    name: 'home',
    title: '其他应用首页',
    url: '/job/home',
  },
  {
    name: 'Organization',
    title: '用户管理',
    url: '/system-manager/user',
    children: [
      { name: 'user_group', title: '组织架构', url: '/system-manager/user/structure' },
      { name: 'login_auth', title: '登录认证', url: '/system-manager/user/login-auth' },
    ],
  },
  {
    name: 'application_list',
    title: '应用管理',
    url: '/system-manager/application',
    children: [
      { name: 'application_role', title: '角色', url: '/system-manager/application/manage/role' },
    ],
  },
  {
    name: 'credential',
    title: '凭据管理',
    url: '/system-manager/credential',
  },
];

const permissionMenus: Menu[] = [
  {
    name: 'Organization',
    display_name: 'Organization',
    children: [
      { name: 'user_group', display_name: 'User&Group', operation: ['View', 'Add User'] },
      { name: 'login_auth', display_name: 'Login Auth', operation: ['View'] },
    ],
  },
  {
    name: 'Application',
    display_name: 'Application',
    children: [
      { name: 'application_list', display_name: 'Application list', operation: ['View', 'Edit'] },
      { name: 'application_role', display_name: 'Application role', operation: ['View'] },
    ],
  },
  {
    name: 'Setting',
    display_name: 'Setting',
    children: [
      { name: 'unknown_setting_item', display_name: 'Unknown Item', operation: ['View'] },
    ],
  },
];

describe('localizePermissionMenus', () => {
  it('用当前应用菜单的 name 替换展示名，并保留权限 id 与操作', () => {
    const localized = localizePermissionMenus(permissionMenus, appMenus, 'system-manager');
    const organization = localized[0];

    expect(organization.display_name).toBe('用户管理');
    expect(organization.name).toBe('Organization');
    expect(organization.children?.[0]).toMatchObject({
      name: 'user_group',
      display_name: '组织架构',
      operation: ['View', 'Add User'],
    });
    expect(organization.children?.[1].display_name).toBe('登录认证');
  });

  it('父级 name 对不上时，用已经包住这些权限 id 的菜单标题', () => {
    const localized = localizePermissionMenus(
      [
        ...permissionMenus,
        {
          name: 'Credential',
          display_name: 'Credential',
          children: [
            { name: 'credential', display_name: 'Credential', operation: ['View', 'Add'] },
          ],
        },
      ],
      appMenus,
      'system-manager',
    );

    expect(localized[1].name).toBe('Application');
    expect(localized[1].display_name).toBe('应用管理');
    expect(localized[1].children?.[0]).toMatchObject({
      name: 'application_list',
      display_name: '应用管理',
      operation: ['View', 'Edit'],
    });
    expect(localized[3].display_name).toBe('凭据管理');
    expect(localized[3].children?.[0]).toMatchObject({
      name: 'credential',
      display_name: '凭据管理',
      operation: ['View', 'Add'],
    });
    expect(localized[2].display_name).toBe('Setting');
    expect(localized[2].children?.[0].display_name).toBe('Unknown Item');
  });

  it('子项落到不同分组时，父级保留接口原文', () => {
    const menus: AppMenuTitleNode[] = [
      { name: 'services', title: '服务', url: '/apm/services' },
      { name: 'traces', title: '探索', url: '/apm/explore' },
    ];
    const localized = localizePermissionMenus(
      [{
        name: 'Explore',
        display_name: 'Explore',
        children: [
          { name: 'services', display_name: 'Services', operation: ['View'] },
          { name: 'traces', display_name: 'Traces', operation: ['View'] },
        ],
      }],
      menus,
      'apm',
    );

    expect(localized[0].display_name).toBe('Explore');
    expect(localized[0].children?.[0].display_name).toBe('服务');
    expect(localized[0].children?.[1].display_name).toBe('探索');
  });

  it('后端 client id 按映射找到前端应用菜单', () => {
    const menus: AppMenuTitleNode[] = [
      {
        name: 'cloud_region_list',
        title: '云区域',
        url: '/node-manager/cloudregion',
        children: [
          { name: 'cloud_region_node', title: '节点', url: '/node-manager/cloudregion/node' },
        ],
      },
      {
        name: 'home',
        title: '补丁首页',
        url: '/patch-manager/home',
      },
      {
        name: 'cloud_region_list',
        title: '不该命中的云区域',
        url: '/job/cloudregion',
      },
    ];
    const localized = localizePermissionMenus(
      [
        {
          name: 'Cloud Region',
          display_name: 'Cloud Region',
          children: [
            { name: 'cloud_region_list', display_name: 'Cloud Region List', operation: ['View'] },
            { name: 'cloud_region_node', display_name: 'Cloud Region Node', operation: ['View'] },
          ],
        },
        {
          name: 'Home',
          display_name: 'Home',
          children: [
            { name: 'home', display_name: 'Home', operation: ['View'] },
          ],
        },
      ],
      menus,
      'node',
    );

    expect(localized[0].display_name).toBe('云区域');
    expect(localized[0].children?.[0]).toMatchObject({
      name: 'cloud_region_list',
      display_name: '云区域',
      operation: ['View'],
    });
    expect(localized[0].children?.[1].display_name).toBe('节点');
    expect(localized[1].display_name).toBe('Home');

    const patchLocalized = localizePermissionMenus(
      [{ name: 'home', display_name: 'Home', operation: ['View'] }],
      menus,
      'patch',
    );
    expect(patchLocalized[0].display_name).toBe('补丁首页');
  });

  it('name 按原样比较，organization 对不上 Organization', () => {
    const menus: AppMenuTitleNode[] = [
      { name: 'organization', title: 'User Management', url: '/system-manager/user' },
    ];
    const localized = localizePermissionMenus(
      [{ name: 'Organization', display_name: 'Organization' }],
      menus,
      'system-manager',
    );

    expect(localized[0].display_name).toBe('Organization');
  });
});
