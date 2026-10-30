import { describe, expect, it } from 'vitest';
import type { TreeNode } from '@/app/cmdb/types/autoDiscovery';
import {
  countPluginTasks,
  filterCatalogCategories,
  getTaskStatusStats,
  reconcilePluginGroups,
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

  it('resolves a custom script task to its plugin, not the builtin model plugin', () => {
    const catalog: TreeNode[] = [
      {
        id: 'host_manage',
        key: 'host_manage',
        name: '主机',
        tabItems: [
          {
            id: 'host',
            key: 'host',
            name: '主机',
            model_id: 'host',
            type: 'job',
            task_type: 'host',
          },
        ],
      },
      {
        id: 'custom_script',
        key: 'custom_script',
        name: '自定义',
        tabItems: [
          {
            id: 'custom_host_linux_scan',
            key: 'custom_host_linux_scan',
            name: '主机Linux采集',
            model_id: 'host',
            type: 'job',
            task_type: 'custom_script',
            custom_plugin_pk: 7,
          },
        ],
      },
    ];

    expect(
      resolveCollectPlugin(catalog, {
        model_id: 'host',
        driver_type: 'job',
        params: { custom_plugin_pk: 7, os_type: 'linux' },
      })?.id,
    ).toBe('custom_host_linux_scan');
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
    expect(countPluginTasks({ total: 1, not_start: 1, success: 0, failed: 0, running: 0 })).toBe(1);
    expect(countPluginTasks(null)).toBe(0);
  });

  it('数据调和分组不含容器，Docker 虽是中间件也不进入', () => {
    const groups = reconcilePluginGroups([
      {
        id: 'k8s',
        key: 'k8s',
        name: '容器',
        tabItems: [
          { id: 'k8s_cluster', key: 'k8s_cluster', name: 'K8S', model_id: 'k8s_cluster', task_type: 'k8s' },
          { id: 'docker', key: 'docker', name: 'Docker', model_id: 'docker', task_type: 'middleware' },
        ],
      },
      {
        id: 'databases',
        key: 'databases',
        name: '数据库',
        tabItems: [
          { id: 'mysql', key: 'mysql', name: 'MySQL', model_id: 'mysql', task_type: 'protocol' },
        ],
      },
      {
        id: 'vmware',
        key: 'vmware',
        name: '虚拟化',
        tabItems: [
          { id: 'vmware_vc', key: 'vmware_vc', name: 'vCenter', model_id: 'vmware_vc', task_type: 'vm' },
        ],
      },
    ]);
    expect(groups.map((group) => group.name)).toEqual(['数据库']);
  });

  it('自定义插件只看自己的任务数，不借用同模型内置插件的统计', () => {
    const plugin = {
      id: 'custom_win_host',
      model_id: 'host',
      type: 'job',
      task_type: 'custom_script',
      custom_plugin_pk: 7,
    };
    expect(
      getTaskStatusStats(
        {
          'host__job': { success: 4, failed: 0, running: 0 },
          custom_script__7: { success: 0, failed: 0, running: 0, not_start: 1, total: 1 },
        },
        plugin,
      )?.total,
    ).toBe(1);
    expect(getTaskStatusStats({ 'host__job': { success: 4, failed: 0, running: 0 } }, plugin)).toBeUndefined();
  });
});
