import { describe, expect, it } from 'vitest';
import type { TreeNode } from '@/app/cmdb/types/autoDiscovery';
import {
  countPluginTasks,
  filterCatalogCategories,
  resolveCollectPlugin,
} from '../pluginCatalog';

const host = (id: string, name: string, type = 'protocol'): TreeNode => ({
  id,
  key: id,
  name,
  model_id: id,
  type,
});

const categories: TreeNode[] = [
  {
    id: 'all',
    key: 'all',
    name: 'All',
    tabItems: [],
  },
  {
    id: 'database',
    key: 'database',
    name: '数据库',
    tabItems: [host('mysql', 'MySQL'), host('redis', 'Redis', 'job')],
  },
  {
    id: 'server',
    key: 'server',
    name: '主机服务器',
    tabItems: [
      {
        id: 'physcial_server_ipmi',
        key: 'physcial_server_ipmi',
        name: 'IPMI',
        model_id: 'physcial_server',
        type: 'protocol',
      },
      {
        id: 'physcial_server_redfish',
        key: 'physcial_server_redfish',
        name: 'Redfish',
        model_id: 'physcial_server',
        type: 'protocol',
      },
    ],
  },
];

describe('plugin catalog', () => {
  it('filters plugins by name and hides empty categories', () => {
    const groups = filterCatalogCategories(categories, 'redis');
    expect(groups.map((group) => group.category.id)).toEqual(['database']);
    expect(groups[0].plugins.map((plugin) => plugin.id)).toEqual(['redis']);
  });

  it('skips the synthetic all category', () => {
    const groups = filterCatalogCategories(categories, '');
    expect(groups.map((group) => group.category.id)).toEqual(['database', 'server']);
  });

  it('resolves a task to its plugin, including physical server protocols', () => {
    expect(
      resolveCollectPlugin(categories, {
        model_id: 'mysql',
        driver_type: 'protocol',
      })?.name,
    ).toBe('MySQL');
    expect(
      resolveCollectPlugin(categories, {
        model_id: 'physcial_server',
        driver_type: 'protocol',
        params: { collection_protocol: 'redfish' },
      })?.name,
    ).toBe('Redfish');
    expect(
      resolveCollectPlugin(categories, {
        model_id: 'physcial_server',
        driver_type: 'protocol',
      })?.id,
    ).toBe('physcial_server_ipmi');
  });

  it('counts running, success, failed and partial tasks', () => {
    expect(
      countPluginTasks({
        running: 1,
        success: 2,
        failed: 3,
        partial_success: 4,
      }),
    ).toBe(10);
    expect(countPluginTasks(null)).toBe(0);
  });
});
