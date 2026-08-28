export interface OrganizationPathNode {
  id: string | number;
  name: string;
  children?: OrganizationPathNode[];
  subGroups?: OrganizationPathNode[];
}

export const buildOrganizationPathMap = (
  tree: OrganizationPathNode[] = []
): Map<string, string> => {
  const pathById = new Map<string, string>();
  const visit = (nodes: OrganizationPathNode[], parentPath: string[]) => {
    nodes.forEach((node) => {
      const path = [...parentPath, node.name];
      pathById.set(String(node.id), path.join(' / '));
      visit(node.subGroups || node.children || [], path);
    });
  };
  visit(tree, []);
  return pathById;
};

export const formatAlertOrganizationPath = (
  teamIds: Array<string | number> | null | undefined,
  pathById: Map<string, string>,
  nameById?: Map<string, string>
): string => {
  if (!teamIds?.length) return '';
  return teamIds
    .map((id) => {
      const key = String(id);
      return pathById.get(key) || nameById?.get(key) || '';
    })
    .filter(Boolean)
    .join('，');
};
