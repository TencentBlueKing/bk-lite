import {
  consumeRoleListLoadingMock,
  roleTreeResponse,
} from '../../../src/stories/system-manager-user-org-modal.fixtures';

const users = [
  {
    id: 'u-1001',
    username: 'alice',
    email: 'alice@example.com',
    phone: '13800000001',
    display_name: 'Alice Zhang',
    name: 'Alice Zhang',
    team: 'Backend Team',
    role: 'Edit Dashboard',
    roles: [{ id: '1002', name: 'Edit Dashboard' }],
    group_role_list: ['Edit Dashboard'],
    groups: [{ id: '11', rules: { monitor: 2 } }],
    last_login: '2026-06-03 09:00:00',
    status: 'normal',
    is_superuser: false,
    created_at: '2026-05-01 10:00:00',
  },
  {
    id: 'u-1002',
    username: 'bob',
    email: 'bob@example.com',
    phone: '13800000002',
    display_name: 'Bob Chen',
    name: 'Bob Chen',
    team: 'Frontend Team',
    role: 'View Topology',
    roles: [{ id: '2001', name: 'View Topology' }],
    group_role_list: ['View Topology'],
    groups: [{ id: '12', rules: { cmdb: 1 } }],
    last_login: '2026-06-02 11:30:00',
    status: 'disabled',
    is_superuser: false,
    created_at: '2026-05-04 12:00:00',
  },
  {
    id: 'u-9000',
    username: 'root',
    email: 'root@example.com',
    phone: '13800000000',
    display_name: 'Root Admin',
    name: 'Root Admin',
    team: 'Default',
    role: 'Monitor',
    roles: [{ id: '1001', name: 'View Dashboard' }],
    group_role_list: ['View Dashboard'],
    groups: [{ id: '1', rules: { monitor: 1 } }],
    last_login: '2026-06-03 08:00:00',
    status: 'normal',
    is_superuser: true,
    created_at: '2026-04-20 09:00:00',
  },
];

const orgTree = [
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

const clientDetails: Record<string, { name: string; display_name: string; description: string }> = {
  'system-manager': {
    name: 'system-manager',
    display_name: 'System Manager',
    description: 'System manager application',
  },
  monitor: {
    name: 'monitor',
    display_name: 'Monitor',
    description: 'Monitor application',
  },
  cmdb: {
    name: 'cmdb',
    display_name: 'CMDB',
    description: 'CMDB application',
  },
};

const buildRoleTree = () => roleTreeResponse;

const pickUser = (userId?: string) => users.find((user) => user.id === userId) || users[0];

export const useUserApi = () => {
  function getUsersList(params: {
    is_superuser?: number;
    group_id?: string | number;
    search?: string;
    page?: number;
    page_size?: number;
  } = {}) {
    const filtered = users.filter((user) => {
      const matchesSuperuser = typeof params.is_superuser === 'number'
        ? (params.is_superuser === 1 ? user.is_superuser : !user.is_superuser)
        : true;
      const matchesGroup = params.group_id
        ? user.groups.some((group) => String(group.id) === String(params.group_id))
        : true;
      const matchesSearch = params.search
        ? [user.username, user.display_name, user.email, user.team].some((value) => value?.includes(params.search || ''))
        : true;
      return matchesSuperuser && matchesGroup && matchesSearch;
    });

    return Promise.resolve({
      count: filtered.length,
      users: filtered,
    });
  }

  const getOrgTree = async () => orgTree;

  const getClientDetail = async (request: { params?: { name?: string | null } } = {}) => {
    const name = request.params?.name || 'system-manager';
    return clientDetails[name] || clientDetails['system-manager'];
  };

  const getRoleList = async () => {
    if (consumeRoleListLoadingMock()) {
      await new Promise((resolve) => {
        setTimeout(resolve, 1200);
      });
    }

    return buildRoleTree();
  };

  const getUserDetail = async (request: { user_id?: string } = {}) => {
    const user = pickUser(request.user_id);
    return {
      username: user.username,
      email: user.email,
      phone: user.phone,
      display_name: user.display_name,
      timezone: 'Asia/Shanghai',
      locale: 'en',
      is_superuser: user.is_superuser,
      groups: user.groups,
      roles: user.roles.map((role) => ({ role_id: Number(role.id) })),
    };
  };

  const addUser = async () => ({ success: true });
  const editUser = async () => ({ success: true });
  const deleteUser = async () => ({ success: true });
  const setUserPassword = async () => ({ success: true });
  const changeUserStatus = async () => ({
    action: 'enable',
    total: 1,
    success_ids: [1001],
    skipped: [],
  });

  return {
    getUsersList,
    getOrgTree,
    getClientDetail,
    getRoleList,
    getUserDetail,
    editUser,
    addUser,
    deleteUser,
    setUserPassword,
    changeUserStatus,
  };
};
