import { describe, expect, it } from 'vitest';

import {
  areAllRelationshipsExpanded,
  getDefaultExpandedRelationshipKeys,
  mergeRelationshipAssociations,
} from '../relationshipMenuData';

describe('relationship menu data', () => {
  it('没有关联实例时仍保留全部模型关联定义', () => {
    const definitions = [
      { model_asst_id: 'switch-belongs-interface' },
      { model_asst_id: 'switch-contains-rack' },
    ];

    expect(mergeRelationshipAssociations([], definitions)).toEqual(definitions);
  });

  it('有关联实例时使用实例数量，并补齐零数据的关联定义', () => {
    const instance = {
      model_asst_id: 'switch-belongs-interface',
      inst_list: [{ inst_uuid: 'interface-1' }],
    };
    const definitions = [
      { model_asst_id: 'switch-belongs-interface' },
      { model_asst_id: 'switch-contains-rack' },
    ];

    expect(mergeRelationshipAssociations([instance], definitions)).toEqual([
      instance,
      definitions[1],
    ]);
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
