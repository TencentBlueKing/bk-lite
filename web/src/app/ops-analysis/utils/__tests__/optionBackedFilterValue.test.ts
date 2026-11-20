import { describe, expect, test } from 'vitest';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import {
  reconcileOptionBackedFilterValue,
  retainFilterValueInOptions,
  retainOpeningFilterValues,
} from '@/app/ops-analysis/utils/optionBackedFilterValue';
import { syncFilterValuesWithDefinitions } from '@/app/ops-analysis/utils/unifiedFilterState';
import { processDataSourceParams } from '@/app/ops-analysis/utils/widgetDataTransform';

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

  test('还没写入时按选项求交，对不上或用户清空时不放宽、不套回旧默认', () => {
    expect(
      reconcileOptionBackedFilterValue(hostFilter(['host-a', 'host-b']), undefined, HOSTS),
    ).toEqual(['host-b']);
    expect(
      reconcileOptionBackedFilterValue(hostFilter(['host-a', 'host-b']), null, HOSTS, 'reset'),
    ).toEqual(['host-b']);
    expect(
      reconcileOptionBackedFilterValue(hostFilter(['host-a', 'host-b']), null, HOSTS),
    ).toBeUndefined();
    expect(
      reconcileOptionBackedFilterValue(hostFilter(['host-a']), ['host-a'], []),
    ).toBeNull();
    expect(
      reconcileOptionBackedFilterValue(hostFilter(['host-a']), ['user-kept'], HOSTS),
    ).toBeNull();
    expect(
      reconcileOptionBackedFilterValue(hostFilter(['host-a', 'host-b']), ['host-a', 'host-b'], HOSTS),
    ).toEqual(['host-b']);
    expect(
      reconcileOptionBackedFilterValue(hostFilter(0), 0, []),
    ).toBeNull();
    expect(
      reconcileOptionBackedFilterValue(hostFilter(0), 0, [{ label: '零', value: 0 }]),
    ).toBeUndefined();
    expect(
      reconcileOptionBackedFilterValue(hostFilter(false), false, []),
    ).toBeUndefined();
  });

  test('选项失败时已存默认值仍进入查询，0、空串和 false 不被当成未设置', () => {
    const definition = hostFilter(['host-a']);
    const values = syncFilterValuesWithDefinitions([definition], {});
    expect(values.instance_ids__string).toEqual(['host-a']);
    expect(
      retainOpeningFilterValues([definition], { instance_ids__string: ['host-a'] }),
    ).toEqual({ instance_ids__string: ['host-a'] });
    expect(
      syncFilterValuesWithDefinitions([definition], { instance_ids__string: null })
        .instance_ids__string,
    ).toBeNull();
    expect(
      syncFilterValuesWithDefinitions([definition], { instance_ids__string: ['user-kept'] })
        .instance_ids__string,
    ).toEqual(['user-kept']);

    const zero = hostFilter(0);
    zero.id = 'count__number';
    zero.key = 'count';
    zero.type = 'number';
    expect(syncFilterValuesWithDefinitions([zero], {})[zero.id]).toBe(0);

    const blank = hostFilter('');
    if (blank.inputConfig?.control === 'select') {
      blank.inputConfig = { ...blank.inputConfig, multiple: false };
    }
    expect(syncFilterValuesWithDefinitions([blank], {})[blank.id]).toBe('');
    const emptyMulti = hostFilter([]);
    expect(syncFilterValuesWithDefinitions([emptyMulti], {})[emptyMulti.id]).toEqual([]);

    const request = processDataSourceParams({
      sourceParams: [{
        name: 'instance_ids',
        type: 'string',
        filterType: 'filter',
        value: null,
        inputConfig: definition.inputConfig,
      }, {
        name: 'enabled',
        type: 'boolean',
        filterType: 'params',
        value: false,
      }],
      unifiedFilterValues: values,
      filterBindings: { [definition.id]: true },
      filterDefinitions: [definition],
      userParams: { enabled: false },
    });
    expect(request.instance_ids).toEqual(['host-a']);
    expect(request.enabled).toBe(false);
  });
});
