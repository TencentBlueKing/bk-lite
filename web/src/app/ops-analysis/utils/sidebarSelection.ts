import type { Key } from 'react';

interface ResolveSidebarTreeSelectionInput {
  selectedKeys: Key[];
  nodeKey: Key;
  selected: boolean;
}

interface SidebarTreeSelectionResult {
  selectedKeys: Key[];
  navigationKey: string | null;
}

export const resolveSidebarTreeSelection = ({
  selectedKeys,
  nodeKey,
  selected,
}: ResolveSidebarTreeSelectionInput): SidebarTreeSelectionResult => {
  if (!selected) {
    return {
      selectedKeys: [nodeKey],
      navigationKey: null,
    };
  }

  const nextSelectedKeys = selectedKeys.length > 0 ? selectedKeys : [nodeKey];
  return {
    selectedKeys: nextSelectedKeys,
    navigationKey: String(nextSelectedKeys[0]),
  };
};
