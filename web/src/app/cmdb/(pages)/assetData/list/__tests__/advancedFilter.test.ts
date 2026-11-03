import { describe, expect, it } from 'vitest';

import {
  buildPathCascader,
  buildPathChoices,
  cascaderValueToPath,
  choiceForDepth,
  conditionValueText,
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

  it('按字段类型给出运算符', () => {
    expect(operatorsFor('str').map((item) => item.label)).toEqual(['等于', '不等于', '包含', '不包含', '为空', '不为空']);
    expect(operatorsFor('time').map((item) => item.value)).toContain('time<');
    expect(operatorNeedsValue('empty')).toBe(false);
    expect(operatorNeedsValue('str=')).toBe(true);
  });
});
