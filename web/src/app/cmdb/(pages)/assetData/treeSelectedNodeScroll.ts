import { buildGroupKey } from './treeExpansionPreference';

export const ASSET_MODEL_TREE_NODE_ATTR = 'data-asset-model-id';

export interface AssetModelTreeGroup {
  classification_id: string;
  list: Array<{ model_id: string }>;
}

export type FirstVisitTreeScrollPlan =
  | { action: 'wait' }
  | { action: 'skip' }
  | { action: 'expand'; groupKey: string }
  | { action: 'scroll'; modelId: string };

export const findClassificationIdForModel = (
  modelGroup: AssetModelTreeGroup[],
  modelId: string
): string | null => {
  if (!modelId) return null;
  const group = modelGroup.find((item) =>
    item.list.some((model) => model.model_id === modelId)
  );
  return group?.classification_id ?? null;
};

export const planFirstVisitTreeScroll = (input: {
  alreadyAttempted: boolean;
  selectedModelId: string;
  treeLoaded: boolean;
  modelGroup: AssetModelTreeGroup[];
  expandedKeys: string[];
}): FirstVisitTreeScrollPlan => {
  if (input.alreadyAttempted) return { action: 'skip' };
  if (!input.treeLoaded) return { action: 'wait' };
  if (!input.selectedModelId) return { action: 'skip' };

  const classificationId = findClassificationIdForModel(
    input.modelGroup,
    input.selectedModelId
  );
  if (!classificationId) return { action: 'skip' };

  const groupKey = buildGroupKey(classificationId);
  if (!input.expandedKeys.includes(groupKey)) {
    return { action: 'expand', groupKey };
  }
  return { action: 'scroll', modelId: input.selectedModelId };
};

export const shouldFinishFirstVisitTreeScroll = (input: {
  didScroll: boolean;
  loading: boolean;
}): boolean => input.didScroll || !input.loading;

export const queryAssetModelTreeNode = (
  container: ParentNode | null,
  modelId: string
): HTMLElement | null => {
  if (!container || !modelId) return null;
  const nodes = container.querySelectorAll<HTMLElement>(
    `[${ASSET_MODEL_TREE_NODE_ATTR}]`
  );
  for (const node of nodes) {
    if (node.getAttribute(ASSET_MODEL_TREE_NODE_ATTR) === modelId) {
      return node;
    }
  }
  return null;
};

export const scrollElementIntoContainer = (
  container: HTMLElement | null,
  element: HTMLElement | null
): boolean => {
  if (!container || !element) return false;
  try {
    const target =
      (element.closest('.ant-tree-treenode') as HTMLElement | null) ?? element;
    const containerRect = container.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const offsetTop = targetRect.top - containerRect.top + container.scrollTop;
    const nextScrollTop =
      offsetTop - (container.clientHeight - targetRect.height) / 2;
    container.scrollTop = Math.max(0, nextScrollTop);
    return true;
  } catch {
    return false;
  }
};
