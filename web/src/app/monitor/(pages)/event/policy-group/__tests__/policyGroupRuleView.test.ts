import { describe, expect, it } from 'vitest';
import { filterAndSortRules, pluginCounts, type PolicyGroupRule } from '../policyGroupRuleView';

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
});
