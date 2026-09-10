export interface LevelNodeItem {
  id: string;
  parentId: string | null;
}

export interface LevelNodes {
  [level: number]: LevelNodeItem[];
}

export interface LookupStats {
  comparisons: number;
}

export function buildFirstLevelIndex(levelNodes: LevelNodes): Map<string, number> {
  const index = new Map<string, number>();
  const levels = Object.keys(levelNodes)
    .map(Number)
    .filter((level) => Number.isFinite(level))
    .sort((a, b) => a - b);

  for (const level of levels) {
    const nodes = levelNodes[level];
    if (!nodes) continue;
    for (const item of nodes) {
      if (!index.has(item.id)) {
        index.set(item.id, level);
      }
    }
  }

  return index;
}

export function lookupFirstLevel(
  index: Map<string, number>,
  id: string,
  stats?: LookupStats
): number | undefined {
  if (stats) {
    stats.comparisons += 1;
  }
  return index.get(id);
}

export function resolveTopoEdgeEndpoints(
  type: string,
  id: string,
  parentId: string
): { source: string; target: string } {
  return {
    source: type === 'src' ? parentId : id,
    target: type === 'dst' ? parentId : id,
  };
}
