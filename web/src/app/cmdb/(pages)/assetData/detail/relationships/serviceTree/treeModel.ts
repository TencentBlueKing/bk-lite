export type ServiceTreeKind = string;

export interface ServiceTreeLayerAction {
  model_id: string;
  model_name: string;
}

export interface ServiceTreeNode {
  inst_uuid: string;
  inst_name: string;
  kind: ServiceTreeKind;
  model_name?: string;
  depth: number;
  host_count: number;
  create_layers?: ServiceTreeLayerAction[];
  can_create_application?: boolean;
  children?: ServiceTreeNode[];
}

export const ASSIGN_HOST_PAGE_SIZE = 20;

export function canAssignHosts(kind: ServiceTreeKind): boolean {
  return kind === 'application';
}

export function hostsForAction<T extends { inst_uuid: string }>(
  hosts: T[],
  selectedUuids: string[],
): T[] {
  const wanted = new Set(selectedUuids);
  return hosts.filter((item) => wanted.has(item.inst_uuid));
}

export function mergePageSelection(
  previous: string[],
  pageUuids: string[],
  selectedOnPage: string[],
): string[] {
  const page = new Set(pageUuids);
  const selected = new Set(selectedOnPage);
  const offPage = new Set([
    ...previous.filter((uuid) => !page.has(uuid)),
    ...selectedOnPage.filter((uuid) => !page.has(uuid)),
  ]);
  return [...offPage, ...pageUuids.filter((uuid) => selected.has(uuid))];
}

export function hostCandidateQuery(keyword: string): { field: string; type: string; value: string }[] {
  const value = keyword.trim();
  if (!value) return [];
  return [{ field: 'inst_name', type: 'str*', value }];
}

export function transferAppLabel(app: { inst_name?: string; system_name?: string } | null | undefined): string {
  const name = (app?.inst_name || '').trim();
  const system = (app?.system_name || '').trim();
  if (system && name) return `${system} / ${name}`;
  return name || system;
}

export function createLayerActions(
  node: Pick<ServiceTreeNode, 'create_layers'> | null | undefined,
): ServiceTreeLayerAction[] {
  return node?.create_layers || [];
}

export function canCreateApplication(
  node: Pick<ServiceTreeNode, 'kind' | 'can_create_application'> | null | undefined,
): boolean {
  if (!node) return false;
  if (typeof node.can_create_application === 'boolean') {
    return node.can_create_application;
  }
  return node.kind === 'system';
}

export function flattenApplications(node: ServiceTreeNode): ServiceTreeNode[] {
  const found: ServiceTreeNode[] = [];
  const walk = (current: ServiceTreeNode) => {
    if (current.kind === 'application') {
      found.push(current);
    }
    (current.children || []).forEach(walk);
  };
  walk(node);
  return found;
}

export function collectTreeKeys(node: ServiceTreeNode): string[] {
  return [node.inst_uuid, ...(node.children || []).flatMap(collectTreeKeys)];
}

export function toAntdTree(node: ServiceTreeNode): {
  title: string;
  key: string;
  kind: ServiceTreeKind;
  depth: number;
  host_count: number;
  children?: ReturnType<typeof toAntdTree>[];
} {
  return {
    title: node.inst_name,
    key: node.inst_uuid,
    kind: node.kind,
    depth: node.depth,
    host_count: node.host_count,
    children: (node.children || []).map(toAntdTree),
  };
}
