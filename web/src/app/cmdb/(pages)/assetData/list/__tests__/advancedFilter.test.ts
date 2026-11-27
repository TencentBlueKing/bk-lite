import { describe, expect, it } from 'vitest';

import {
  buildPathCascader,
  buildPathChoices,
  cascaderValueToPath,
  choiceForDepth,
  conditionValueText,
  displayFieldCondition,
  exportFilterPayload,
  operatorNeedsValue,
  operatorsFor,
  summarizeCondition,
  type AssocEdge,
} from '../advancedFilter';

const edges: Record<string, AssocEdge[]> = {
  mysql: [
    { model_asst_id: 'mysql_run_host', src_model_id: 'mysql', dst_model_id: 'host', asst_id: 'run' },
    { model_asst_id: 'host_run_mysql', src_model_id: 'host', dst_model_id: 'mysql', asst_id: 'run' },
    { model_asst_id: 'mysql_connect_host', src_model_id: 'mysql', dst_model_id: 'host', asst_id: 'connect' },
  ],
  host: [
    { model_asst_id: 'mysql_run_host', src_model_id: 'mysql', dst_model_id: 'host', asst_id: 'run' },
    { model_asst_id: 'host_belong_cluster', src_model_id: 'host', dst_model_id: 'cluster', asst_id: 'belong' },
  ],
};

describe('高级筛选路径和摘要', () => {
  const choices = buildPathChoices(
    'mysql',
    edges,
    (asstId) => ({ run: '运行于', connect: '关联', belong: '属于' }[asstId || ''] || asstId || ''),
    (modelId) => ({ mysql: 'MySQL', host: '主机', cluster: '集群' }[modelId] || modelId),
  );

  it('同一端模型的不同关系按源和目标分开，两跳不走原路', () => {
    expect(choices.map((item) => item.label)).toEqual([
      '当前模型',
      'MySQL 运行于 主机',
      'MySQL 运行于 主机 > 主机 属于 集群',
      '主机 运行于 MySQL',
      '主机 运行于 MySQL > MySQL 运行于 主机',
      '主机 运行于 MySQL > 主机 属于 集群',
      'MySQL 关联 主机',
      'MySQL 关联 主机 > MySQL 运行于 主机',
      'MySQL 关联 主机 > 主机 属于 集群',
    ]);
    expect(choices.find((item) => item.path.join() === 'mysql_run_host')?.endModelId).toBe('host');
    expect(choices.find((item) => item.path.join() === 'host_run_mysql')?.endModelId).toBe('host');
    expect(choices.some((item) => item.path.join() === 'mysql_run_host,mysql_run_host')).toBe(false);
  });

  it('一跳可以直接选中，二跳只出现在该关系下面', () => {
    const tree = buildPathCascader(choices);
    expect(tree.map((item) => item.label)).toEqual(['当前模型', 'MySQL 运行于 主机', '主机 运行于 MySQL', 'MySQL 关联 主机']);
    expect(tree[1].children?.map((item) => item.label)).toEqual(['主机 属于 集群']);
    expect(tree[2].children?.map((item) => item.label)).toEqual(['MySQL 运行于 主机', '主机 属于 集群']);
    expect(cascaderValueToPath(['current'])).toEqual([]);
    expect(cascaderValueToPath(['mysql_run_host'])).toEqual(['mysql_run_host']);
    expect(cascaderValueToPath(['mysql_run_host', 'host_belong_cluster'])).toEqual(['mysql_run_host', 'host_belong_cluster']);
  });

  it('筛选范围只决定新增条件的默认层级', () => {
    expect(choiceForDepth(choices, 0).path).toEqual([]);
    expect(choiceForDepth(choices, 1).path).toEqual(['mysql_run_host']);
    expect(choiceForDepth(choices, 2).path).toEqual(['mysql_run_host', 'host_belong_cluster']);
  });

  it('当前模型条件不带路径前缀，关联条件带路径', () => {
    expect(summarizeCondition('当前模型', '数据库版本', '包含', '8.0')).toBe('数据库版本 包含 8.0');
    expect(summarizeCondition('运行于主机', '操作系统', '等于', 'Linux')).toBe('运行于主机.操作系统 等于 Linux');
    expect(summarizeCondition('运行于主机', '操作系统', '为空', '')).toBe('运行于主机.操作系统 为空');
  });

  it('导出全部才带上快速搜索和高级筛选', () => {
    const advanced = { logic: 'AND' as const, conditions: [{ path: ['mysql_run_host'], field: 'os_type', type: 'str=', value: 'Linux' }] };
    const query = [{ field: 'version', type: 'str*', value: '8.0' }];
    expect(exportFilterPayload('all', query, advanced)).toEqual({ query_list: query, advanced_filter: advanced });
    expect(exportFilterPayload('selected', query, advanced)).toEqual({});
    expect(exportFilterPayload('currentPage', query, advanced)).toEqual({});
    expect(exportFilterPayload('all', [], null)).toEqual({});
    expect(conditionValueText({ type: 'time', start: '2026-01-01 00:00', end: '2026-01-02 00:00' })).toBe('2026-01-01 00:00~2026-01-02 00:00');
    expect(conditionValueText({ type: 'empty' })).toBe('');
  });

  it('映射字段显示选项名，原始 id 只在没有映射时保留', () => {
    const labels = { boolYes: '是', boolNo: '否' };
    expect(displayFieldCondition(
      { type: 'list_any[]', value: ['1'] },
      { attr_id: 'os_type', attr_type: 'enum', option: [{ id: 1, name: 'Linux' }, { id: '2', name: 'Windows' }] },
    )).toBe('Linux');
    expect(displayFieldCondition(
      { type: 'list_any[]', value: [1, '2'] },
      { attr_id: 'os_type', attr_type: 'enum', option: [{ id: '1', name: 'Linux' }, { id: 2, name: 'Windows' }] },
    )).toBe('Linux, Windows');
    expect(displayFieldCondition(
      { type: 'str=', value: 'linux' },
      { attr_id: 'os_type', attr_type: 'enum', option: [{ id: 'linux', name: 'Linux' }] },
    )).toBe('Linux');
    expect(displayFieldCondition(
      { type: 'list_any[]', value: ['9'] },
      { attr_id: 'os_type', attr_type: 'enum', option: [{ id: '1', name: 'Linux' }] },
    )).toBe('9');
    expect(displayFieldCondition(
      { type: 'list[]', value: ['9'] },
      { attr_id: 'owner', attr_type: 'user' },
      { users: [{ id: 9, username: 'ada', display_name: 'Ada' }] },
    )).toBe('Ada(ada)');
    expect(displayFieldCondition(
      { type: 'list[]', value: ['404'] },
      { attr_id: 'owner', attr_type: 'user' },
      { users: [] },
    )).toBe('404');
    expect(displayFieldCondition(
      { type: 'list[]', value: [1, 2] },
      { attr_id: 'org', attr_type: 'organization' },
      { groups: [{ id: '1', name: '总部', subGroups: [{ id: 2, name: '研发' }] }] },
    )).toBe('总部, 总部 / 研发');
    expect(displayFieldCondition(
      { type: 'bool', value: false },
      { attr_id: 'active', attr_type: 'bool' },
      labels,
    )).toBe('否');
    expect(displayFieldCondition(
      { type: 'list_any[]', value: ['a%3Ab:c'] },
      { attr_id: 'tag', attr_type: 'tag', option: { mode: 'free', options: [{ key: 'a:b', value: 'c' }] } },
    )).toBe('a:b:c');
    expect(displayFieldCondition(
      { type: 'list_any[]', value: ['env%3Aname:prod'] },
      { attr_id: 'tag', attr_type: 'tag', option: { mode: 'free', options: [] } },
    )).toBe('env:name:prod');
    expect(displayFieldCondition(
      { type: 'int=', value: 0 },
      { attr_id: 'cloud', attr_type: 'int' },
      { clouds: [{ proxy_id: '0', proxy_name: 'default' }] },
    )).toBe('default');
    expect(displayFieldCondition(
      { type: 'int=', value: 0 },
      { attr_id: 'cloud_id', attr_type: 'int' },
      { clouds: [{ proxy_id: 0, proxy_name: 'default' }] },
    )).toBe('default');
    expect(displayFieldCondition(
      { type: 'str=', value: '100%' },
      { attr_id: 'name', attr_type: 'str' },
    )).toBe('100%');
    expect(displayFieldCondition(
      { type: 'str*', value: '8.0' },
      { attr_id: 'version', attr_type: 'str' },
    )).toBe('8.0');
    expect(displayFieldCondition({ type: 'empty' }, { attr_type: 'enum' })).toBe('');
    expect(displayFieldCondition(
      { type: 'time', start: '2026-01-01 00:00', end: '2026-01-02 00:00' },
      { attr_type: 'time' },
    )).toBe('2026-01-01 00:00~2026-01-02 00:00');
  });

  it('按字段类型给出运算符', () => {
    expect(operatorsFor('str').map((item) => item.label)).toEqual(['等于', '不等于', '包含', '不包含', '为空', '不为空']);
    expect(operatorsFor('time').map((item) => item.value)).toContain('time<');
    expect(operatorNeedsValue('empty')).toBe(false);
    expect(operatorNeedsValue('str=')).toBe(true);
  });
});
