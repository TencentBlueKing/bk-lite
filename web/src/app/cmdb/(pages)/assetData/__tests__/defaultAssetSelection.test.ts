import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import type { ModelItem } from '@/app/cmdb/types/assetManage';
import { resolveDefaultAssetSelection } from '../defaultAssetSelection';

const model = (
  modelId: string,
  classificationId: string,
): ModelItem => ({
  model_id: modelId,
  classification_id: classificationId,
  model_name: modelId,
  icn: modelId,
});

const groups = [
  { classification_id: 'empty_top', list: [] as ModelItem[] },
  {
    classification_id: 'host_manage',
    list: [model('host', 'host_manage'), model('virtual_machine', 'host_manage')],
  },
  {
    classification_id: 'database',
    list: [model('mysql', 'database')],
  },
];

describe('资产页默认模型', () => {
  it('第一分组为空时加载后面第一个有模型的分组的第一个模型', () => {
    expect(resolveDefaultAssetSelection(groups)).toEqual({
      groupId: 'host_manage',
      modelId: 'host',
      models: groups[1].list,
    });
  });

  it('地址指定的分组有模型时用该分组的第一个模型', () => {
    expect(resolveDefaultAssetSelection(groups, 'database')).toMatchObject({
      groupId: 'database',
      modelId: 'mysql',
    });
  });

  it('地址指定的分组为空时跳到第一个有模型的分组', () => {
    expect(resolveDefaultAssetSelection(groups, 'empty_top')).toMatchObject({
      groupId: 'host_manage',
      modelId: 'host',
    });
  });

  it('地址指定的模型存在时继续打开该模型', () => {
    expect(resolveDefaultAssetSelection(groups, 'empty_top', 'mysql')).toMatchObject({
      groupId: 'database',
      modelId: 'mysql',
    });
  });

  it('地址里的模型已不存在时改用指定分组的第一个模型', () => {
    expect(resolveDefaultAssetSelection(groups, 'database', 'missing')).toMatchObject({
      groupId: 'database',
      modelId: 'mysql',
    });
  });

  it('所有分组都没有模型时不选模型', () => {
    expect(resolveDefaultAssetSelection([
      { classification_id: 'empty_top', list: [] },
    ])).toBeNull();
    expect(resolveDefaultAssetSelection([])).toBeNull();
  });

  it('资产页通过分组树选择默认模型', () => {
    const source = readFileSync(resolve(__dirname, '../page.tsx'), 'utf8');
    expect(source).toContain('resolveDefaultAssetSelection(groups, assetClassificationId, assetModelId)');
    expect(source).not.toContain('filteredModels[0].key');
    expect(source).not.toContain('groupData[0].classification_id');
  });
});
