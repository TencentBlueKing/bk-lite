interface OrganizationNode {
  id?: string | number;
  value?: string | number;
  name?: string;
  label?: string;
  parentId?: string | number;
  parent_id?: string | number;
}

const sameId = (left: string | number | undefined, right: string | number | undefined) => (
  left != null && right != null && String(left) === String(right)
);

const findOrganization = (groups: OrganizationNode[], target: string | number) => (
  groups.find((item) => sameId(item.id ?? item.value, target)) || null
);

const organizationPath = (organization: OrganizationNode, groups: OrganizationNode[]) => {
  const path: string[] = [];
  let current: OrganizationNode | null = organization;
  const seen = new Set<string>();
  while (current) {
    const marker = String(current.id ?? current.value ?? '');
    if (seen.has(marker)) break;
    seen.add(marker);
    const name = current.name || current.label;
    if (name) path.unshift(name);
    const parentId = current.parent_id ?? current.parentId;
    current = parentId == null || parentId === '' ? null : findOrganization(groups, parentId);
  }
  return path.join('/');
};

export function organizationDisplayText(
  value: Array<string | number> | null | undefined,
  groups: OrganizationNode[],
) {
  if (!value?.length) return '--';
  const names = value
    .map((item) => {
      const organization = findOrganization(groups, item);
      return organization ? organizationPath(organization, groups) : '';
    })
    .filter(Boolean);
  return names.length ? names.join('，') : '--';
}
