import type {
  WikiDirectoryNode,
  WikiExistingStructureDirectory,
  WikiFrozenStructureSnapshot,
} from "@/app/opspilot/types/wiki";

export const collectDirectorySubtreeIds = (
  roots: WikiDirectoryNode[],
  targetId: number,
): number[] | null => {
  const findNode = (nodes: WikiDirectoryNode[]): WikiDirectoryNode | null => {
    for (const node of nodes) {
      if (node.id === targetId) return node;
      const nested = findNode(node.children || []);
      if (nested) return nested;
    }
    return null;
  };
  const target = findNode(roots);
  if (!target) return null;
  const ids: number[] = [];
  const walk = (node: WikiDirectoryNode) => {
    ids.push(node.id);
    (node.children || []).forEach(walk);
  };
  walk(target);
  return ids;
};

export const isTopLevelDirectory = (
  roots: WikiDirectoryNode[],
  directoryId: number,
): boolean => roots.some((node) => node.id === directoryId);

export const canDeleteKnowledgeDirectory = (
  roots: WikiDirectoryNode[],
  directory: WikiDirectoryNode,
  unclassifiedDirectoryId: number | null,
): boolean => {
  if (directory.is_system) return false;
  if (unclassifiedDirectoryId != null && directory.id === unclassifiedDirectoryId) {
    return false;
  }
  return !isTopLevelDirectory(roots, directory.id);
};

export const pageIdsInDirectories = (
  pages: Array<{ id: number; directory: number | null }>,
  directoryIds: Iterable<number>,
): number[] => {
  const allowed = new Set(directoryIds);
  return pages
    .filter((page) => page.directory != null && allowed.has(page.directory))
    .map((page) => page.id);
};

export const omitDirectoriesFromSnapshot = (
  snapshot: WikiFrozenStructureSnapshot,
  omitIds: Iterable<number>,
): WikiExistingStructureDirectory[] => {
  const omitted = new Set(omitIds);
  return snapshot.directories
    .filter((directory) => !omitted.has(directory.id))
    .map((directory) => ({
      kind: "existing",
      id: directory.id,
      key: directory.key,
      origin: directory.origin,
      status: directory.status,
      name: directory.name,
      description: directory.description,
      order: directory.order,
      rules: {
        allowed_page_types: [...directory.rules.allowed_page_types],
        default_for_page_types: [...directory.rules.default_for_page_types],
      },
      parent: directory.parent ? { ...directory.parent } : null,
    }));
};
