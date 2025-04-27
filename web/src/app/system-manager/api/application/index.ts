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
    getAppData
  };
};
