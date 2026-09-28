import { describe, expect, test } from 'vitest';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import {
  deferDynamicOptionFilterValues,
  reconcileOptionBackedFilterValue,
  retainFilterValueInOptions,
} from '@/app/ops-analysis/utils/optionBackedFilterValue';
import { syncFilterValuesWithDefinitions } from '@/app/ops-analysis/utils/unifiedFilterState';

const HOSTS = [
  { label: '可见主机', value: 'host-b' },
];

const hostFilter = (
  defaultValue: UnifiedFilterDefinition['defaultValue'],
): UnifiedFilterDefinition => ({
  id: 'instance_ids__string',
  key: 'instance_ids',
  name: '主机',
  type: 'string',
  order: 0,
  enabled: true,
  defaultValue,
  inputConfig: {
    control: 'select',
    multiple: true,
    optionsSource: {
      type: 'dynamic',
      sourceRef: { type: 'rest_api', value: 'monitor/get_host_instance_list' },
      valueField: 'instance_id',
      labelField: 'display_name',
    },
  },
});

describe('跨组织导入的动态选项默认值', () => {
  test('选项里没有的主机 ID 从多选默认值里去掉', () => {
    expect(retainFilterValueInOptions(['host-a', 'host-b'], HOSTS)).toEqual(['host-b']);
    expect(retainFilterValueInOptions(['host-a'], HOSTS)).toBeNull();
    expect(retainFilterValueInOptions('host-a', HOSTS)).toBeNull();
    expect(retainFilterValueInOptions('host-b', HOSTS)).toBe('host-b');
  });

  test('当前还没选时，用默认值和当前选项求交', () => {
    expect(
      reconcileOptionBackedFilterValue(hostFilter(['host-a', 'host-b']), null, HOSTS),
    ).toEqual(['host-b']);
    expect(
      reconcileOptionBackedFilterValue(hostFilter(['host-a']), null, []),
    ).toBeUndefined();
  });

  test('打开画布时不把动态选项默认值直接套进查询', () => {
    const definition = hostFilter(['host-a']);
    const values = syncFilterValuesWithDefinitions([definition], {});
    expect(values.instance_ids__string).toBeUndefined();
    expect(
      deferDynamicOptionFilterValues([definition], { instance_ids__string: ['host-a'] }),
    ).toEqual({ instance_ids__string: null });
  });
});
