import { describe, expect, it } from 'vitest';
import {
  diffGroupTemplates,
  filterAndSortRules,
  filterPolicyGroupMembers,
  memberTemplateFilterOptions,
  pluginColumnFilters,
  pluginCounts,
  readRuleTableFilters,
  rulesForTemplateIds,
  templateIdsFromRules,
  type PolicyGroupRule,
} from '../policyGroupRuleView';

const rule = (
  name: string,
  plugin_name: string,
  extras: Partial<PolicyGroupRule> = {}
): PolicyGroupRule => ({
  id: extras.id || name.length,
  name,
  plugin_name,
  threshold: extras.threshold || [],
  no_data_enabled: extras.no_data_enabled,
  ...extras,
});

describe('策略组规则展示', () => {
  it('按模板统计规则数，不把空模板算进 Host', () => {
    expect(
      pluginCounts([
        rule('CPU', 'Host'),
        rule('内存', 'Host'),
        rule('磁盘', 'Windows WMI'),
        rule('未标注', ''),
      ])
    ).toEqual([
      { name: 'Host', count: 2 },
      { name: 'Windows WMI', count: 1 },
      { name: '其他', count: 1 },
    ]);
  });

  it('先按模板再按名称排序，并可用模板和无数据过滤', () => {
    const rules = [
      rule('磁盘', 'Host'),
      rule('CPU', 'Windows WMI', { no_data_enabled: true }),
      rule('内存', 'Host', { no_data_enabled: true }),
    ];
    expect(filterAndSortRules(rules, { pluginFilter: 'all', noData: null, keyword: '' }).map((item) => item.name)).toEqual([
      '内存',
      '磁盘',
      'CPU',
    ]);
    expect(
      filterAndSortRules(rules, { pluginFilter: 'Host', noData: 'on', keyword: '' }).map((item) => item.name)
    ).toEqual(['内存']);
    expect(
      filterAndSortRules(rules, { pluginFilter: 'all', noData: null, keyword: 'cpu' }).map((item) => item.name)
    ).toEqual(['CPU']);
  });

  it('按来源模板做差集，没有模板来源的规则不参与勾选', () => {
    const rules = [
      rule('CPU', 'Host', { source_template_id: 1 }),
      rule('磁盘', 'Host', { source_template_id: 2 }),
      rule('手工', 'Host', { source_template_id: null }),
    ];
    expect(templateIdsFromRules(rules)).toEqual([1, 2]);
    expect(diffGroupTemplates([1, 2], [2, 3])).toEqual({ addedIds: [3], removedIds: [1] });
    expect(rulesForTemplateIds(rules, [1]).map((item) => item.name)).toEqual(['CPU']);
  });

  it('按生效模板筛出对应对象，没有匹配插件的实例不出现', () => {
    const members = [
      {
        instance_id: 'win-01',
        name: 'win-01',
        plugins: [{ id: 1, name: 'Windows WMI' }],
        templates: [{ id: 11, rule_id: 1, name: 'WMI CPU', plugin_name: 'Windows WMI' }],
      },
      {
        instance_id: 'web-01',
        name: 'web-01',
        plugins: [{ id: 2, name: 'Host' }],
        templates: [{ id: 22, rule_id: 2, name: '磁盘读取速率过高', plugin_name: 'Host' }],
      },
    ];
    expect(filterPolicyGroupMembers(members, { keyword: '', filter: 'plugin:Host' }).map((item) => item.name)).toEqual([
      'web-01',
    ]);
    expect(filterPolicyGroupMembers(members, { keyword: '', filter: 'template:11' }).map((item) => item.name)).toEqual([
      'win-01',
    ]);
    const options = memberTemplateFilterOptions([
      rule('磁盘读取速率过高', 'Host', { source_template_id: 22, id: 2 }),
    ]);
    expect(options).toEqual([
      {
        label: 'Host (Linux Agent)',
        options: [
          { label: 'Host (Linux Agent) 全部对象', value: 'plugin:Host' },
          { label: '磁盘读取速率过高', value: 'template:22' },
        ],
      },
    ]);
  });
});

describe('规则表筛选', () => {
  it('模板筛选项带规则数，并按名称排序', () => {
    expect(pluginColumnFilters([
      { name: 'Windows WMI', count: 2 },
      { name: 'Host', count: 4 },
    ])).toEqual([
      { text: 'Host (4)', value: 'Host' },
      { text: 'Windows WMI (2)', value: 'Windows WMI' },
    ]);
  });

  it('列头未选时视为全部，无数据只接受开关两个值', () => {
    expect(readRuleTableFilters(undefined)).toEqual({ noData: null, plugin: 'all' });
    expect(readRuleTableFilters({ plugin_name: ['Host'], no_data_enabled: ['on'] })).toEqual({
      noData: 'on',
      plugin: 'Host',
    });
    expect(readRuleTableFilters({ no_data_enabled: ['maybe'] })).toEqual({ noData: null, plugin: 'all' });
  });
});
