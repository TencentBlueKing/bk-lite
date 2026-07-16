import type { CmdbOrganizationNode } from './types';

const findOrganizationById = (
  groups: CmdbOrganizationNode[],
  targetValue: string | number | undefined,
) => {
  for (let i = 0; i < groups.length; i += 1) {
    if (groups[i].id === targetValue || groups[i].value === targetValue) {
      return groups[i];
    }
  }

  return null;
};

const getOrganizationFullPath = (
  organization: CmdbOrganizationNode | null,
  flatGroups: CmdbOrganizationNode[],
): string => {
  if (!organization) return '';

  const path: string[] = [];
  let current: CmdbOrganizationNode | null = organization;

  while (current) {
    const name = current.name || current.label;
    if (name) {
      path.unshift(name);
    }

    const parentId = current.parent_id || current.parentId;
    current = parentId
      ? findOrganizationById(flatGroups, parentId)
      : null;
  }

  return path.join('/');
};

export const getOrganizationDisplayText = (
  value: string | number | Array<string | number> | null | undefined,
  flatGroups: CmdbOrganizationNode[],
) => {
  if (Array.isArray(value)) {
    if (value.length === 0) return '--';

    const groupNames = value
      .map((item) => {
        const organization = findOrganizationById(flatGroups || [], item);
        return organization ? getOrganizationFullPath(organization, flatGroups || []) : null;
      })
      .filter((name): name is string => Boolean(name));

    return groupNames.length > 0 ? groupNames.join('，') : '--';
  }

  const organization = findOrganizationById(flatGroups || [], value);
  const fullPath = organization ? getOrganizationFullPath(organization, flatGroups || []) : '';
  return fullPath || '--';
};
