import {
  groupDataRulePageResponse,
  groupDataRuleResponse,
  roleTreeResponse,
} from '../../../src/stories/system-manager-user-org-modal.fixtures';

const appModules = [
  {
    name: 'monitor',
    display_name: 'Monitor',
    children: [
      { name: 'dashboard', display_name: 'Dashboard' },
      { name: 'alert', display_name: 'Alert' },
    ],
  },
  {
    name: 'cmdb',
    display_name: 'CMDB',
    children: [
      { name: 'topology', display_name: 'Topology' },
    ],
  },
];

const flatRoles = roleTreeResponse.flatMap((module) => [
  ...module.children.map((child) => ({
    id: child.id,
    name: child.name,
  })),
]);

const menus = [
  {
    name: 'dashboard',
    display_name: 'Dashboard',
    operation: ['view', 'operate'],
  },
  {
    name: 'topology',
    display_name: 'Topology',
    operation: ['view', 'operate'],
  },
];

export const useRoleApi = () => {
  const getRoles = async () => flatRoles;

  const addRole = async () => ({ success: true });
  const updateRole = async () => ({ success: true });
  const deleteRole = async () => ({ success: true });

  const getUsersByRole = async () => ({
    count: 1,
    items: [
      {
        id: 'u-1001',
        name: 'Alice Zhang',
        group: 'Backend Team',
        roles: ['Edit Dashboard'],
        username: 'alice',
        display_name: 'Alice Zhang',
      },
    ],
  });

  const getAllUser = async () => ([
    {
      id: 'u-1001',
      name: 'Alice Zhang',
      group: 'Backend Team',
      roles: ['Edit Dashboard'],
      username: 'alice',
      display_name: 'Alice Zhang',
    },
    {
      id: 'u-1002',
      name: 'Bob Chen',
      group: 'Frontend Team',
      roles: ['View Topology'],
      username: 'bob',
      display_name: 'Bob Chen',
    },
  ]);

  const getRoleMenus = async () => (['dashboard-view', 'dashboard-operate']);
  const getAllMenus = async () => menus;
  const setRoleMenus = async () => ({ success: true });

  const addUser = async () => ({ success: true });
  const deleteUser = async () => ({ success: true });

  const getGroupDataRule = async (request: {
    params?: { group_id?: string | number; app?: string; search?: string };
  }) => {
    if (request.params?.group_id) {
      return groupDataRuleResponse;
    }

    return groupDataRulePageResponse;
  };

  const deleteGroupDataRule = async () => ({ success: true });
  const addGroupDataRule = async () => ({ success: true });
  const updateGroupDataRule = async () => ({ success: true });

  const getAppData = async () => groupDataRuleResponse;
  const getAppModules = async () => appModules;

  const addApplication = async () => ({ success: true });
  const updateApplication = async () => ({ success: true });
  const deleteApplication = async () => ({ success: true });

  const getRoleGroups = async () => ({
    count: 2,
    items: [
      { id: 11, name: 'Backend Team', parent_id: 1, description: 'Backend engineering' },
      { id: 12, name: 'Frontend Team', parent_id: 1, description: 'Frontend engineering' },
    ],
  });

  const addRoleGroups = async () => ({ success: true });
  const deleteRoleGroups = async () => ({ success: true });

  const getCustomMenus = async () => [];
  const getCustomMenuDetail = async () => ({ id: 1, name: 'Default Menu' });
  const addCustomMenu = async () => ({ success: true });
  const updateCustomMenu = async () => ({ success: true });
  const deleteCustomMenu = async () => ({ success: true });
  const toggleCustomMenuStatus = async () => ({ success: true });
  const copyCustomMenu = async () => ({ success: true });

  return {
    getRoles,
    addRole,
    updateRole,
    deleteRole,
    getUsersByRole,
    getAllUser,
    getRoleMenus,
    getAllMenus,
    setRoleMenus,
    addUser,
    deleteUser,
    getGroupDataRule,
    deleteGroupDataRule,
    addGroupDataRule,
    updateGroupDataRule,
    getAppData,
    getAppModules,
    addApplication,
    updateApplication,
    deleteApplication,
    getRoleGroups,
    addRoleGroups,
    deleteRoleGroups,
    getCustomMenus,
    getCustomMenuDetail,
    addCustomMenu,
    updateCustomMenu,
    deleteCustomMenu,
    toggleCustomMenuStatus,
    copyCustomMenu,
  };
};
