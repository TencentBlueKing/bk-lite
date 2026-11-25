import { describe, expect, it } from 'vitest';

import { builtinMenusForCopy } from '@/app/system-manager/hooks/useCustomMenuPage';
import type { MenuItem } from '@/types/index';

const menu = (item: Partial<MenuItem> & Pick<MenuItem, 'name' | 'url'>): MenuItem => ({
  title: item.title || item.name,
  icon: 'icon',
  operation: [],
  ...item,
});

describe('builtinMenusForCopy', () => {
  it('keeps visible top-level pages that have no children', () => {
    const copied = builtinMenusForCopy([
      menu({ name: 'search', url: '/cmdb/assetSearch', title: '搜索' }),
      menu({
        name: 'asset_info',
        url: '/cmdb/assetData',
        title: '资产',
        children: [
          menu({ name: 'asset_basic_information', url: '/cmdb/assetData/detail/baseInfo', title: '基础信息' }),
        ],
      }),
      menu({ name: 'workflow_entry', url: '/workflow', title: '入口', isNotMenuItem: true }),
      menu({ name: 'other', url: '/log/search', title: '日志' }),
    ], 'cmdb');

    expect(copied).toEqual([
      { name: 'search', title: '搜索', url: '/cmdb/assetSearch', icon: 'icon' },
      {
        name: 'asset_info',
        title: '资产',
        url: '/cmdb/assetData',
        icon: 'icon',
        children: [
          {
            name: 'asset_basic_information',
            title: '基础信息',
            url: '/cmdb/assetData/detail/baseInfo',
            icon: 'icon',
          },
        ],
      },
    ]);
  });

  it('keeps hasDetail, hidden flags, and children below the first level', () => {
    const source = [
      menu({
        name: 'application_list',
        url: '/system-manager/application',
        title: '应用管理',
        hasDetail: true,
        children: [
          menu({
            name: 'custom_menu',
            url: '/system-manager/application/manage/menu',
            title: '自定义菜单',
            children: [
              {
                title: '菜单配置',
                url: '/system-manager/application/manage/menu/config',
                icon: 'icon',
                operation: [],
                name: '',
                isNotMenuItem: true,
              },
            ],
          }),
        ],
      }),
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
    ];

    expect(builtinMenusForCopy(source, 'system-manager')).toEqual([
      {
        name: 'application_list',
        title: '应用管理',
        url: '/system-manager/application',
        icon: 'icon',
        hasDetail: true,
        children: [
          {
            name: 'custom_menu',
            title: '自定义菜单',
            url: '/system-manager/application/manage/menu',
            icon: 'icon',
            children: [
              {
                title: '菜单配置',
                url: '/system-manager/application/manage/menu/config',
                icon: 'icon',
                isNotMenuItem: true,
              },
            ],
          },
        ],
      },
      {
        name: 'channel_list',
        title: '通知渠道',
        url: '/system-manager/channel',
        icon: 'icon',
        children: [
          {
            name: 'channel_setting',
            title: '设置',
            url: '/system-manager/channel/detail/settings',
            icon: 'icon',
            isNotMenuItem: true,
          },
        ],
      },
    ]);
  });
});
