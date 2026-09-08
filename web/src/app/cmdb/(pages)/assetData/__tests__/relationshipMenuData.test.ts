import { describe, expect, it } from 'vitest';

import { mergeRelationshipAssociations } from '../relationshipMenuData';

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
});
