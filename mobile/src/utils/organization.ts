const GUEST_GROUP_NAME = 'OpsPilotGuest';

export interface OrganizationGroup {
  id: string;
  name: string;
  subGroups?: OrganizationGroup[];
}

function asGroupId(value: unknown): string | null {
  if (value == null || value === '') return null;
  return String(value);
}

function nestedGroups(node: Record<string, unknown>): unknown {
  return node.subGroups ?? node.children;
}

export function normalizeGroupTree(
  input: unknown,
  options?: { includeGuest?: boolean },
): OrganizationGroup[] {
  if (!Array.isArray(input)) return [];

  const includeGuest = options?.includeGuest === true;
  const result: OrganizationGroup[] = [];

  for (const item of input) {
    if (!item || typeof item !== 'object') continue;
    const node = item as Record<string, unknown>;
    const id = asGroupId(node.id);
    if (!id) continue;

    const name = String(node.name ?? '');
    if (!includeGuest && name === GUEST_GROUP_NAME) continue;

    const subGroups = normalizeGroupTree(nestedGroups(node), options);
    result.push({
      id,
      name,
      subGroups: subGroups.length > 0 ? subGroups : undefined,
    });
  }

  return result;
}

export function findGroupById(
  groups: OrganizationGroup[],
  id: string | null | undefined,
): OrganizationGroup | null {
  if (!id) return null;

  for (const group of groups) {
    if (group.id === id) return group;
    const nested = findGroupById(group.subGroups || [], id);
    if (nested) return nested;
  }

  return null;
}

export function collectGroupIds(groups: OrganizationGroup[]): string[] {
  const ids: string[] = [];
  const walk = (items: OrganizationGroup[]) => {
    items.forEach((item) => {
      ids.push(item.id);
      if (item.subGroups) walk(item.subGroups);
    });
  };
  walk(groups);
  return ids;
}

export function filterGroupTree(
  groups: OrganizationGroup[],
  search: string,
): OrganizationGroup[] {
  const keyword = search.trim().toLowerCase();
  if (!keyword) return groups;

  const result: OrganizationGroup[] = [];
  for (const group of groups) {
    const matches = group.name.toLowerCase().includes(keyword);
    const filteredSubGroups = filterGroupTree(group.subGroups || [], search);
    if (matches || filteredSubGroups.length > 0) {
      result.push({
        ...group,
        subGroups: filteredSubGroups.length > 0 ? filteredSubGroups : group.subGroups,
      });
    }
  }

  return result;
}

export function resolveGroupName(
  tree: OrganizationGroup[],
  teamId: string | null,
  fallbackList?: unknown,
): string {
  const fromTree = findGroupById(tree, teamId);
  if (fromTree?.name) return fromTree.name;

  const fallbackTree = normalizeGroupTree(fallbackList, { includeGuest: true });
  return findGroupById(fallbackTree, teamId)?.name || '';
}

export function buildSelectableGroupTree(
  groupTree: unknown,
  groupList: unknown,
  isSuperuser?: boolean,
): OrganizationGroup[] {
  const includeGuest = Boolean(isSuperuser);
  const tree = normalizeGroupTree(groupTree, { includeGuest });
  if (tree.length > 0) return tree;
  return normalizeGroupTree(groupList, { includeGuest });
}

export function buildOrganizationScope(
  userId: unknown,
  teamId: string | null | undefined,
  includeChildren: boolean,
): string {
  return `${userId || 0}:${teamId || 'none'}:${includeChildren ? '1' : '0'}`;
}
