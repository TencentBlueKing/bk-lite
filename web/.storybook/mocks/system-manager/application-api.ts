import {
  groupDataRulePageResponse,
  groupDataRuleResponse,
  roleTreeResponse,
} from '../../../src/stories/system-manager-user-org-modal.fixtures';
import type { CustomMenu, CustomMenuListResponse } from '../../../src/app/system-manager/types/menu';

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

const customMenus: CustomMenu[] = [
  {
    id: 1,
    app: 'monitor',
    display_name: 'Default Menu',
    description: 'Built-in menu for monitor',
    is_enabled: true,
    is_build_in: true,
    menu_count: 2,
    created_at: '2026-06-03 08:00:00',
    updated_at: '2026-06-03 08:15:00',
    created_by: 'system',
    updated_by: 'alice',
    domain: 'domain.com',
    updated_by_domain: 'domain.com',
  },
  {
    id: 2,
    app: 'cmdb',
    display_name: 'CMDB Custom Menu',
    description: 'Storybook-friendly CMDB menu',
    is_enabled: false,
    is_build_in: false,
    menu_count: 1,
    created_at: '2026-06-03 08:30:00',
    updated_at: '2026-06-03 08:45:00',
    created_by: 'bob',
    updated_by: 'bob',
    domain: 'domain.com',
    updated_by_domain: 'domain.com',
  },
];

const customMenuDetails = [
  {
    ...customMenus[0],
    menus: [
      {
        name: 'dashboard',
        title: 'Dashboard',
        url: '/system-manager/monitor/dashboard',
        icon: 'dashboard',
        children: [
          {
            name: 'dashboard-overview',
            title: 'Overview',
            url: '/system-manager/monitor/dashboard/overview',
            icon: 'overview',
          },
          {
            name: 'dashboard-alert',
            title: 'Alert',
            url: '/system-manager/monitor/dashboard/alert',
            icon: 'alert',
          },
        ],
      },
    ],
  },
  {
    ...customMenus[1],
    menus: [
      {
        name: 'topology',
        title: 'Topology',
        url: '/system-manager/cmdb/topology',
        icon: 'topology',
      },
    ],
  },
];

const normalizeText = (value?: string) => value?.trim().toLowerCase() || '';

const getCustomMenuParams = (request: {
  params?: { app?: string; page?: number; page_size?: number; search?: string };
} = {}) => request.params || {};

const filterCustomMenus = (request: {
  params?: { app?: string; page?: number; page_size?: number; search?: string };
} = {}) => {
  const { app, page = 1, page_size = customMenus.length, search } = getCustomMenuParams(request);
  const normalizedApp = normalizeText(app);
  const normalizedSearch = normalizeText(search);

  const filtered = customMenus.filter((menu) => {
    const matchesApp = normalizedApp ? normalizeText(menu.app) === normalizedApp : true;
    const matchesSearch = normalizedSearch
      ? [menu.display_name, menu.description, menu.app]
        .filter(Boolean)
        .some((value) => normalizeText(value).includes(normalizedSearch))
      : true;

    return matchesApp && matchesSearch;
  });

  const start = Math.max((page - 1) * page_size, 0);
  const items = filtered.slice(start, start + page_size);

  return {
    count: filtered.length,
    items,
  };
};

const pickCustomMenuDetail = (request: {
  id?: number | string;
  app?: string;
  params?: { app?: string };
} = {}) => {
  const requestedId = request.id;
  const requestedApp = normalizeText(request.app || request.params?.app);
  const normalizedId = requestedId === undefined ? undefined : String(requestedId);

  const exactMatch = customMenuDetails.find((menu) => String(menu.id) === normalizedId && (!requestedApp || normalizeText(menu.app) === requestedApp));
  if (exactMatch) {
    return exactMatch;
  }

  if (normalizedId !== undefined) {
    const idMatch = customMenuDetails.find((menu) => String(menu.id) === normalizedId);
    if (idMatch) {
      return idMatch;
    }
  }

  if (requestedApp) {
    return customMenuDetails.find((menu) => normalizeText(menu.app) === requestedApp) || customMenuDetails[0];
  }

  return customMenuDetails[0];
};

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

  const getCustomMenus = async (request: {
    params?: { app?: string; page?: number; page_size?: number; search?: string };
  } = {}): Promise<CustomMenuListResponse> => filterCustomMenus(request);
  const getCustomMenuDetail = async (request: {
    id?: number | string;
    app?: string;
    params?: { app?: string };
  } = {}) => pickCustomMenuDetail(request);
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
