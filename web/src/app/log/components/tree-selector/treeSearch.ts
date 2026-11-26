import { TreeItem } from '@/app/log/types';

export function nodeTitle(node: { title: TreeItem['title'] }): string {
  return typeof node.title === 'string' ? node.title : '';
}

export function expandableTreeKeys(nodes: TreeItem[]): Array<TreeItem['key']> {
  const keys: Array<TreeItem['key']> = [];
  for (const node of nodes) {
    if (node.children?.length) {
      keys.push(node.key, ...expandableTreeKeys(node.children));
    }
  }
  return keys;
}

export function filterTreeByTitle(nodes: TreeItem[], searchValue: string): TreeItem[] {
  const needle = searchValue.toLowerCase();
  return nodes.flatMap((node) => {
    const children = filterTreeByTitle(node.children || [], searchValue);
    if (nodeTitle(node).toLowerCase().includes(needle) || children.length) {
      return [{ ...node, children }];
    }
    return [];
  });
}

export function restoreMatchedBranches(
  filtered: TreeItem[],
  original: TreeItem[],
  searchValue: string
): TreeItem[] {
  const needle = searchValue.toLowerCase();
  return filtered.map((node) => {
    const source = original.find((item) => item.key === node.key);
    const selfMatch = nodeTitle(node).toLowerCase().includes(needle);
    if (
      source &&
      selfMatch &&
      (node.children?.length ?? 0) === 0 &&
      (source.children?.length ?? 0) > 0
    ) {
      return { ...node, children: source.children };
    }
    if (source && (node.children?.length ?? 0) > 0) {
      return {
        ...node,
        children: restoreMatchedBranches(node.children, source.children || [], searchValue)
      };
    }
    return node;
  });
}
