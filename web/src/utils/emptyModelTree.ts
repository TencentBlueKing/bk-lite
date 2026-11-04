export const CMDB_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY = 'cmdb_object_tree_hide_empty_model';
export const MONITOR_OBJECT_TREE_HIDE_EMPTY_MODEL_KEY = 'monitor_object_tree_hide_empty_model';

export interface KeyValueStorage {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

export interface CountedTreeNode {
  count?: number | null;
  children?: CountedTreeNode[];
}

export interface ModelGroupLike<TModel extends { model_id: string }> {
  list: TModel[];
}

const HIDE_EMPTY_MODELS = 'true';
const SHOW_EMPTY_MODELS = 'false';

export const readHideEmptyModels = (
  storage: Pick<KeyValueStorage, 'getItem'> | null,
  key: string
): boolean => {
  try {
    return storage?.getItem(key) === HIDE_EMPTY_MODELS;
  } catch {
    return false;
  }
};

export const writeHideEmptyModels = (
  storage: Pick<KeyValueStorage, 'setItem'> | null,
  key: string,
  hideEmptyModels: boolean
): boolean => {
  try {
    if (!storage) return false;
    storage.setItem(key, hideEmptyModels ? HIDE_EMPTY_MODELS : SHOW_EMPTY_MODELS);
    return true;
  } catch {
    return false;
  }
};

export const browserStorage = (): KeyValueStorage | null => {
  try {
    if (typeof window === 'undefined') return null;
    return window.localStorage;
  } catch {
    return null;
  }
};

export const modelHasInstances = (count: unknown): boolean => {
  const value = typeof count === 'number' ? count : Number(count);
  return Number.isFinite(value) && value > 0;
};

export const treeHasInstanceCounts = (nodes: readonly CountedTreeNode[]): boolean =>
  nodes.some((node) => node.count != null || treeHasInstanceCounts(node.children ?? []));

/**
 * 无实例的模型节点去掉。分组本身没有计数，只在还剩可见子节点时保留。
 * 模型自身无实例、但子模型有实例时保留，避免把有数据的子节点一起藏掉。
 * 没有子节点、也没有计数的节点（如「全部」）保留。
 */
export const omitEmptyCountedNodes = <T extends CountedTreeNode>(nodes: readonly T[]): T[] => {
  const visible: T[] = [];
  nodes.forEach((node) => {
    const children = (node.children ?? []) as T[];
    const visibleChildren = children.length ? omitEmptyCountedNodes(children) : [];
    const isModel = node.count != null;
    const keep = isModel
      ? modelHasInstances(node.count) || visibleChildren.length > 0
      : children.length === 0 || visibleChildren.length > 0;
    if (!keep) return;
    visible.push({ ...node, children: visibleChildren });
  });
  return visible;
};

/** 按模型实例计数去掉空模型，并丢掉因此变空的分组。不修改入参。 */
export const omitEmptyModelGroups = <T extends ModelGroupLike<{ model_id: string }>>(
  groups: readonly T[],
  counts: Record<string, unknown> | null | undefined
): T[] => {
  const countMap = counts && typeof counts === 'object' && !Array.isArray(counts) ? counts : {};
  return groups.flatMap((group) => {
    const list = group.list.filter((model) => modelHasInstances(countMap[model.model_id]));
    if (!list.length) return [];
    return [{ ...group, list }];
  });
};
