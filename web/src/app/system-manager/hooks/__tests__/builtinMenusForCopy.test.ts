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
});
