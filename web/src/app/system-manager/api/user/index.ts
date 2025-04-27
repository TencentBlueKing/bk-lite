import useApiClient from '@/utils/request';
export const useUserApi = () => {
  const { get, post } = useApiClient();

  function getUsersList(params: any) {
    return get('/system_mgmt/user/search_user_list/', { params });
  }
  async function getOrgTree() {
    return await get('/system_mgmt/group/search_group_list/');
  }
  async function getClientDetail(params: any) {
    return await get('/core/api/get_client_detail/', params);
  }
  async function getRoleList(params: any) {
    return await post('/system_mgmt/role/get_role_tree/', params);
  }
  async function getUserDetail(params: any) {
    return await post('/system_mgmt/user/get_user_detail/', params);
  }
  async function addUser(params: any) {
    return await post(`/system_mgmt/user/create_user/`, params)
  }
  async function editUser(params: any) {
    return await post(`/system_mgmt/user/update_user/`, params)
  }
  async function deleteUser(params: any) {
    return await post(`/system_mgmt/user/delete_user/`, params)
  }
  async function setUserPassword(params: any) {
    return await post(`/system_mgmt/user/reset_password/`, params)
  }
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
  }
}
