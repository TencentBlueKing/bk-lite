import type { GroupItem, ModelItem } from '@/app/cmdb/types/assetManage';

export interface DefaultAssetSelection {
  groupId: string;
  modelId: string;
  models: ModelItem[];
}

type AssetGroup = Pick<GroupItem, 'classification_id' | 'list'>;

const firstModelInGroup = (group: AssetGroup | undefined): DefaultAssetSelection | null => {
  const model = group?.list[0];
  if (!group || !model) return null;
  return {
    groupId: group.classification_id,
    modelId: model.model_id,
    models: group.list,
  };
};

/**
 * 资产页初次进入时要打开的模型。
 * 地址里的模型存在就用它；否则用指定分组的第一个模型；
 * 指定分组为空或不存在时，按分组顺序跳过空分组，取第一个有模型的分组的第一个模型。
 */
export const resolveDefaultAssetSelection = (
  groups: AssetGroup[],
  requestedClassificationId = '',
  requestedModelId = '',
): DefaultAssetSelection | null => {
  if (requestedModelId) {
    const groupWithModel = groups.find((group) =>
      group.list.some((item) => item.model_id === requestedModelId),
    );
    if (groupWithModel) {
      return {
        groupId: groupWithModel.classification_id,
        modelId: requestedModelId,
        models: groupWithModel.list,
      };
    }
  }

  const requestedGroup = requestedClassificationId
    ? groups.find(
      (group) => group.classification_id === requestedClassificationId && group.list.length > 0,
    )
    : undefined;
  return firstModelInGroup(requestedGroup ?? groups.find((group) => group.list.length > 0));
};
