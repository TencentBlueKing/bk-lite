import { isCanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import type { DirItem, DirectoryType } from '@/app/ops-analysis/types';

export interface CopyDirectoryOption {
  title: string;
  value: number;
  key: number;
  disabled: boolean;
  children?: CopyDirectoryOption[];
}

export interface CopyGroupOption {
  title: string;
  value: number;
  key: number;
  disabled?: boolean;
  children?: CopyGroupOption[];
}

export const shouldShowCanvasCopyAction = (item: {
  type: DirectoryType;
}): boolean => isCanvasType(item.type);

const BUILTIN_CANVAS_GROUP_EDIT_TYPES = new Set<DirectoryType>([
  'dashboard',
  'topology',
  'architecture',
  'screen',
  'report',
]);

export const isBuiltinDirectory = (item?: {
  type?: DirectoryType;
  is_build_in?: boolean;
} | null): boolean => item?.type === 'directory' && Boolean(item.is_build_in);

/** 内置仪表盘 / 拓扑 / 架构 / 大屏 / 报表可改组织；网络拓扑与数据源不在此列。 */
export const isBuiltinCanvasGroupEditable = (item?: {
  type?: DirectoryType;
  is_build_in?: boolean;
} | null): boolean =>
  Boolean(item?.is_build_in) &&
  item?.type != null &&
  BUILTIN_CANVAS_GROUP_EDIT_TYPES.has(item.type);

export const getSidebarDirectoryMenuKeys = (item: {
  type: DirectoryType;
  is_build_in?: boolean;
}): string[] => {
  if (!isBuiltinDirectory(item)) {
    return [];
  }
  return ['edit'];
};

export const buildDirectoryEditPayload = (
  item: { type?: DirectoryType; is_build_in?: boolean },
  values: { name?: string; desc?: string; groups?: number[] },
): Record<string, unknown> => {
  if (isBuiltinDirectory(item) || isBuiltinCanvasGroupEditable(item)) {
    return { groups: values.groups ?? [] };
  }
  return {
    name: values.name,
    desc: values.desc,
    groups: values.groups,
  };
};

export const getSidebarCanvasMenuKeys = (
  item: {
    type: DirectoryType;
    is_build_in?: boolean;
  },
  options?: { canEditCatalogue?: boolean },
): string[] => {
  if (!isCanvasType(item.type)) {
    return [];
  }
  if (item.is_build_in && isBuiltinCanvasGroupEditable(item)) {
    const resourceKeys = ['copy', 'export'];
    if (options?.canEditCatalogue) {
      return ['editGroup', ...resourceKeys];
    }
    return resourceKeys;
  }
  if (item.is_build_in) {
    return ['copy', 'export', 'edit', 'delete'];
  }
  return ['edit', 'delete', 'copy', 'export'];
};

/** 编辑已有画布时只保留目录链内的组织，不把当前组织补回去。 */
export const retainAllowedGroupIds = (
  selectedGroupIds: number[] | undefined,
  allowedGroupIds: number[],
): number[] => {
  const allowed = new Set(allowedGroupIds);
  return (selectedGroupIds || []).filter((groupId) => allowed.has(groupId));
};

export const buildCopyDirectoryTree = (
  items: DirItem[] | undefined,
): CopyDirectoryOption[] => {
  if (!items?.length) {
    return [];
  }
  return items.flatMap((item) => mapDirectoryOption(item)).filter((node): node is CopyDirectoryOption => Boolean(node));
};

export const collectDirectoryChainGroupIds = (
  items: DirItem[] | undefined,
  directoryId: number | string | null | undefined,
): number[] => {
  if (directoryId == null || directoryId === '') {
    return [];
  }
  const chain = findDirectoryChain(items || [], String(directoryId));
  if (!chain.length) {
    return [];
  }
  return intersectGroupIds(chain.map((directory) => directory.groups || []));
};

export const defaultCopyGroups = (
  allowedGroupIds: number[],
  currentGroupId?: number | null,
): number[] => {
  if (currentGroupId != null && allowedGroupIds.includes(currentGroupId)) {
    return [currentGroupId];
  }
  return [];
};

export const convergeCopyGroups = (
  selectedGroupIds: number[] | undefined,
  allowedGroupIds: number[],
  currentGroupId?: number | null,
): number[] => {
  const allowed = new Set(allowedGroupIds);
  const kept = (selectedGroupIds || []).filter((groupId) => allowed.has(groupId));
  if (kept.length) {
    return kept;
  }
  return defaultCopyGroups(allowedGroupIds, currentGroupId);
};

export const filterGroupTreeByAllowedIds = (
  tree: CopyGroupOption[] | undefined,
  allowedGroupIds: number[],
): CopyGroupOption[] => {
  const allowed = new Set(allowedGroupIds);
  const prune = (nodes: CopyGroupOption[] | undefined): CopyGroupOption[] => {
    if (!nodes?.length) {
      return [];
    }
    return nodes.flatMap((node) => {
      const children = prune(node.children);
      const allowedHere = allowed.has(node.value);
      if (!allowedHere && !children.length) {
        return [];
      }
      return [
        {
          ...node,
          disabled: !allowedHere || Boolean(node.disabled),
          children: children.length ? children : undefined,
        },
      ];
    });
  };
  return prune(tree);
};

export const collectDirectoryExpandKeys = (
  items: DirItem[] | undefined,
  directoryId: number | string | null | undefined,
): string[] => {
  if (directoryId == null || directoryId === '') {
    return [];
  }
  return findDirectoryChain(items || [], String(directoryId)).map((item) => item.id);
};

const mapDirectoryOption = (item: DirItem): CopyDirectoryOption | CopyDirectoryOption[] | null => {
  const childOptions = (item.children || [])
    .flatMap((child) => mapDirectoryOption(child))
    .filter((node): node is CopyDirectoryOption => Boolean(node));

  if (item.type !== 'directory' || item.is_build_in) {
    return childOptions;
  }

  const directoryId = Number(item.data_id);
  if (!Number.isInteger(directoryId)) {
    return childOptions;
  }

  return {
    title: item.name,
    value: directoryId,
    key: directoryId,
    disabled: Boolean(item.is_build_in),
    children: childOptions.length ? childOptions : undefined,
  };
};

const findDirectoryChain = (items: DirItem[], directoryId: string): DirItem[] => {
  for (const item of items) {
    if (item.type === 'directory' && (String(item.data_id) === directoryId || item.id === directoryId || item.id === `directory_${directoryId}`)) {
      return [item];
    }
    if (item.children?.length) {
      const nested = findDirectoryChain(item.children, directoryId);
      if (nested.length) {
        return item.type === 'directory' ? [item, ...nested] : nested;
      }
    }
  }
  return [];
};

const intersectGroupIds = (groupLists: number[][]): number[] => {
  if (!groupLists.length) {
    return [];
  }
  const intersection = groupLists
    .map((groups) => new Set(groups.map(Number).filter((groupId) => Number.isInteger(groupId))))
    .reduce((left, right) => new Set([...left].filter((groupId) => right.has(groupId))));
  return [...intersection];
};
