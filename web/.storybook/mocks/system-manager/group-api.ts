import {
  groupDetailWithRoles,
} from '../../../src/stories/system-manager-user-org-modal.fixtures';

const groupTree = [
  {
    id: '1',
    name: 'Default',
    path: '/Default',
    hasAuth: true,
    is_virtual: false,
    role_ids: [1001],
    subGroups: [
      {
        id: '11',
        name: 'Backend Team',
        path: '/Default/Backend Team',
        hasAuth: true,
        is_virtual: false,
        role_ids: [1002],
        subGroups: [],
        access: {
          manage: true,
          manageMembers: true,
          manageMembership: true,
          view: true,
          viewMembers: true,
        },
      },
      {
        id: '12',
        name: 'Frontend Team',
        path: '/Default/Frontend Team',
        hasAuth: true,
        is_virtual: false,
        role_ids: [2001],
        subGroups: [],
        access: {
          manage: true,
          manageMembers: true,
          manageMembership: true,
          view: true,
          viewMembers: true,
        },
      },
    ],
    access: {
      manage: true,
      manageMembers: true,
      manageMembership: true,
      view: true,
      viewMembers: true,
    },
  },
  {
    id: '2',
    name: 'Virtual Root',
    path: '/Virtual Root',
    hasAuth: true,
    is_virtual: true,
    role_ids: [2002],
    subGroups: [],
    access: {
      manage: true,
      manageMembers: true,
      manageMembership: true,
      view: true,
      viewMembers: true,
    },
  },
];

const frontendGroupDetailWithRoles = {
  group_id: 12,
  group_name: 'Frontend Team',
  allow_inherit_roles: false,
  own_role_ids: [2001],
  inherited_role_ids: [],
  inherited_role_source: '',
  inherited_role_source_map: {},
};

const resolveGroupDetail = (groupId?: string | number) => {
  if (String(groupId) === '12') {
    return frontendGroupDetailWithRoles;
  }

  return groupDetailWithRoles;
};

export const useGroupApi = () => {
  const getTeamData = async () => groupTree;

  const addTeamData = async () => ({ success: true });
  const updateGroup = async () => ({ success: true });
  const deleteTeam = async () => ({ success: true });

  const getGroupRoles = async () => ([
    { id: 1001, name: 'View Dashboard', app: 'monitor' },
    { id: 1002, name: 'Edit Dashboard', app: 'monitor' },
  ]);

  const getGroupDetailWithRoles = async (request?: { group_id?: string | number }) => {
    return resolveGroupDetail(request?.group_id);
  };
  const batchGetGroupDetailWithRoles = async (request?: { group_ids?: Array<string | number> }) => {
    const groupIds = request?.group_ids || [];
    if (groupIds.length === 0) {
      return [groupDetailWithRoles];
    }

    return groupIds.map((groupId) => resolveGroupDetail(groupId));
  };

  return {
    getTeamData,
    addTeamData,
    updateGroup,
    deleteTeam,
    getGroupRoles,
    getGroupDetailWithRoles,
    batchGetGroupDetailWithRoles,
  };
};
