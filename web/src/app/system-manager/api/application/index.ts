import useApiClient from '@/utils/request';
export const useRoleApi = () => {
  const { get, post, put, del } = useApiClient();
  const getRoles = async (params: any) => {
    return await post('/system_mgmt/role/search_role_list/', params);
  }
  const addRole = async (params: any) => {
    return await post('/system_mgmt/role/create_role/', params);
  }
  const updateRole = async (params: any) => {
    return await post('/system_mgmt/role/update_role/', params);
  }
  const deleteRole = async (params: any) => {
    return await post('/system_mgmt/role/delete_role/', params);
  }
  const getUsersByRole = async (params: any) => {
    return await get('/system_mgmt/role/search_role_users/', params);
  }
  const getAllUser = async () => {
    return await get('/system_mgmt/user/user_all/');
  }
  const getRoleMenus = async (params: any) => {
    return await get('/system_mgmt/role/get_role_menus/', params);
  }
  const getAllMenus = async (params: any) => {
    return await get('/system_mgmt/role/get_all_menus/', params);
  }
  const setRoleMenus = async (params: any) => {
    return await post('/system_mgmt/role/set_role_menus/', params);
  }
  const addUser = async (params: any) => {
    return await post('/system_mgmt/role/add_user/', params);
  }
  const deleteUser = async (params: any) => {
    return await post('/system_mgmt/role/delete_user/', params);
  }
  const getGroupDataRule = async (params: any) => {
    return await get('/system_mgmt/group_data_rule/', params);
  }
  const deleteGroupDataRule = async (params: any) => {
    return await del(`/system_mgmt/group_data_rule/${params.id}/`);
  }
  const addGroupDataRule = async (params: any) => {
    return await post('/system_mgmt/group_data_rule/', params);
  }
  const updateGroupDataRule = async (params: any) => {
    return await put(`/system_mgmt/group_data_rule/${params.id}/`, params);
  }
  const getAppData = async (params: any) => {
    return await get('/system_mgmt/group_data_rule/get_app_data/', params);
  }
  const getAppModules = async (params: any) => {
    return await get('/system_mgmt/group_data_rule/get_app_module/', params);
  }
  const addApplication = async (params: any) => {
    return await post('/system_mgmt/app/', params);
  }
  const updateApplication = async (params: any) => {
    return await put(`/system_mgmt/app/${params.id}/`, params);
  }
  const deleteApplication = async (params: any) => {
    return await del(`/system_mgmt/app/${params.id}/`);
  }
  const getRoleGroups = async (params: any) => {
    return await get('/system_mgmt/role/get_role_groups/', params);
  }
  const addRoleGroups = async (params: any) => {
    return await post('/system_mgmt/role/batch_assign_group_roles/', params);
  }
  const deleteRoleGroups = async (params: any) => {
    return await post('/system_mgmt/role/revoke_group_roles/', params);
  }
  const getCustomMenus = async (params: any) => {
    return await get('/system_mgmt/custom_menu_group/', params);
  }
  const getCustomMenuDetail = async (params: any) => {
    return await get(`/system_mgmt/custom_menu_group/${params.id}/`);
  }
  const addCustomMenu = async (params: any) => {
    return await post('/system_mgmt/custom_menu_group/', params);
  }
  const updateCustomMenu = async (params: any) => {
    return await put(`/system_mgmt/custom_menu_group/${params.id}/`, params);
  }
  const deleteCustomMenu = async (params: any) => {
    return await del(`/system_mgmt/custom_menu_group/${params.id}/`);
  }
  const toggleCustomMenuStatus = async (params: any) => {
    return await post(`/system_mgmt/custom_menu_group/${params.id}/change_enable/`, { is_enabled: params.is_enabled });
  }
  const copyCustomMenu = async (params: any) => {
    return await post(`/system_mgmt/custom_menu_group/${params.id}/copy/`, params);
  }
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
    // 新增的菜单管理API
    getCustomMenus,
    getCustomMenuDetail,
    addCustomMenu,
    updateCustomMenu,
    deleteCustomMenu,
    toggleCustomMenuStatus,
    copyCustomMenu
  };
};
