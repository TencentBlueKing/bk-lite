import { describe, expect, it } from 'vitest';
import {
  contextFieldCatalogIncomplete,
  contextFieldOptionsKey,
  mapCmdbContextFieldGroups,
  matchProjectionSourceFilter,
} from '../cmdbContextFieldOptions';

const groups = mapCmdbContextFieldGroups([
  {
    model_id: 'application',
    model_name: '应用',
    fields: [
      { source: 'application.app_id', attr_id: 'app_id', attr_name: '应用ID' },
      { source: 'application.inst_name', attr_id: 'inst_name', attr_name: '应用名称' },
    ],
  },
  {
    model_id: 'system',
    model_name: '应用系统',
    fields: [
      { source: 'system.operator', attr_id: 'operator', attr_name: '运维人员' },
      { source: 'system.inst_name', attr_id: 'inst_name', attr_name: '系统名称' },
    ],
  },
]);

describe('cmdbContextFieldOptions', () => {
  it('把 inst_name 排到每组最前，便于先选名称', () => {
    expect(groups[0].options.map((item) => item.value)).toEqual([
      'application.inst_name',
      'application.app_id',
    ]);
    expect(groups[1].options.map((item) => item.value)).toEqual([
      'system.inst_name',
      'system.operator',
    ]);
  });

  it('缺应用或应用系统组时视为目录未齐，需要再拉一次', () => {
    expect(contextFieldCatalogIncomplete(undefined)).toBe(true);
    expect(
      contextFieldCatalogIncomplete([
        { model_id: 'application', model_name: '应用', fields: [] },
      ])
    ).toBe(true);
    expect(
      contextFieldCatalogIncomplete([
        { model_id: 'application', model_name: '应用', fields: [] },
        { model_id: 'system', model_name: '应用系统', fields: [] },
      ])
    ).toBe(false);
  });

  it('搜「应用系统」能命中运维人员，不依赖中文名里有没有「系统」', () => {
    const operator = groups[1].options.find((item) => item.value === 'system.operator');
    expect(
      matchProjectionSourceFilter('应用系统', operator, groups)
    ).toBe(true);
    expect(
      matchProjectionSourceFilter('系统', { label: '应用系统', options: groups[1].options }, groups)
    ).toBe(true);
  });

  it('目录从只有应用变成含系统时，下拉 key 会变，强制刷新已打开的 AutoComplete', () => {
    const applicationOnly = mapCmdbContextFieldGroups([
      { model_id: 'application', model_name: '应用', fields: [{ source: 'application.inst_name' }] },
    ]);
    expect(contextFieldOptionsKey(applicationOnly)).not.toBe(contextFieldOptionsKey(groups));
  });
});
