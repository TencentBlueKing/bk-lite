import { describe, expect, it } from 'vitest';

import {
  areAllRelationshipsExpanded,
  buildRelationshipMenuSections,
  getDefaultExpandedRelationshipKeys,
  visibleRelationshipAssociations,
} from '../relationshipMenuData';

describe('relationship menu data', () => {
  it('只保留已有关联实例的关系，数量为 0 的不展示', () => {
    expect(visibleRelationshipAssociations([
      { model_asst_id: 'has-data', inst_list: [{ inst_uuid: 'inst-1' }] },
      { model_asst_id: 'empty', inst_list: [] },
      { model_asst_id: 'definition-only' },
    ])).toEqual([
      { model_asst_id: 'has-data', inst_list: [{ inst_uuid: 'inst-1' }] },
    ]);
  });

  it('左侧菜单只展示数量大于 0 的关联，并按关联类型分组', () => {
    expect(buildRelationshipMenuSections({
      instances: [
        {
          model_asst_id: 'host-run-app',
          asst_id: 'run',
          src_model_id: 'application',
          dst_model_id: 'host',
          src_model_name: '应用',
          dst_model_name: '主机',
          inst_list: [{ inst_uuid: 'h1' }, { inst_uuid: 'h2' }],
        },
        {
          model_asst_id: 'host-belong-rack',
          asst_id: 'belong',
          src_model_id: 'host',
          dst_model_id: 'rack',
          src_model_name: '主机',
          dst_model_name: '机柜',
          inst_list: [],
        },
      ],
      assoTypes: [
        { asst_id: 'run', asst_name: '运行' },
        { asst_id: 'belong', asst_name: '属于' },
      ],
      modelId: 'host',
    })).toEqual([
      {
        title: '运行',
        children: [
          { model_asst_id: 'host-run-app', text: '应用', value: 2 },
        ],
      },
    ]);
  });

  it('没有任何已关联实例时左侧不展示关联数量', () => {
    expect(buildRelationshipMenuSections({
      instances: [
        { model_asst_id: 'empty', asst_id: 'run', inst_list: [] },
      ],
      assoTypes: [{ asst_id: 'run', asst_name: '运行' }],
      modelId: 'host',
    })).toEqual([]);
  });

  it('默认只展开有关联实例的分组', () => {
    expect(getDefaultExpandedRelationshipKeys([
      { model_asst_id: 'has-data', inst_list: [{ inst_uuid: 'inst-1' }] },
      { model_asst_id: 'empty', inst_list: [] },
      { model_asst_id: 'definition-only' },
    ])).toEqual(['has-data']);
  });

  it('全部分组展开时才进入全部收起状态', () => {
    expect(areAllRelationshipsExpanded(['a'], ['a', 'b'])).toBe(false);
    expect(areAllRelationshipsExpanded(['a', 'b'], ['a', 'b'])).toBe(true);
    expect(areAllRelationshipsExpanded([], [])).toBe(false);
  });
});
