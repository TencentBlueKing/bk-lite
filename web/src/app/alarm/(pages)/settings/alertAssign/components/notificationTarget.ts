import type { AssignmentNotificationTarget } from '@/app/alarm/types/settings';

export type NotificationTargetType = 'user' | 'organization';

export interface NotificationTargetFormValue {
  target_type?: NotificationTargetType;
  personnel?: string[];
  organization_ids?: number[];
  include_children?: boolean;
}

interface OrganizationTreeNode {
  id: number | string;
  name: string;
  subGroups?: OrganizationTreeNode[];
}

const deduplicate = <T>(values: T[] = []): T[] =>
  Array.from(new Set(values));

export const getNotificationTargetFormValue = (
  target: AssignmentNotificationTarget | undefined,
  legacyPersonnel: string[] = [],
): Required<NotificationTargetFormValue> => {
  if (target?.type === 'organization') {
    return {
      target_type: 'organization',
      personnel: [],
      organization_ids: deduplicate(
        (target.organization_ids || []).map(Number).filter(Number.isFinite),
      ),
      include_children: target.include_children === true,
    };
  }

  return {
    target_type: 'user',
    personnel: deduplicate(target?.usernames || legacyPersonnel || []),
    organization_ids: [],
    include_children: false,
  };
};

export const buildNotificationTarget = (
  value: NotificationTargetFormValue,
): Required<AssignmentNotificationTarget> => {
  if (value.target_type === 'organization') {
    return {
      type: 'organization',
      usernames: [],
      organization_ids: deduplicate(
        (value.organization_ids || []).map(Number).filter(Number.isFinite),
      ),
      include_children: value.include_children === true,
    };
  }

  return {
    type: 'user',
    usernames: deduplicate(value.personnel || []),
    organization_ids: [],
    include_children: false,
  };
};

export const getOrganizationTargetLabels = (
  groupTree: OrganizationTreeNode[],
  organizationIds: number[],
  missingLabel: (id: number) => string = (id) => `#${id}`,
): string[] => {
  const pathById = new Map<number, string>();
  const visit = (nodes: OrganizationTreeNode[], parentPath: string[]) => {
    nodes.forEach((node) => {
      const path = [...parentPath, node.name];
      pathById.set(Number(node.id), path.join(' / '));
      visit(node.subGroups || [], path);
    });
  };
  visit(groupTree || [], []);
  return organizationIds.map(
    (id) => pathById.get(Number(id)) || missingLabel(Number(id)),
  );
};
