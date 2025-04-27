import useApiClient from '@/utils/request';
export const useGroupApi = () => {
  const { get, post } = useApiClient();
  //获取组织列表api
  async function getTeamData() {
    return await get('/system_mgmt/group/search_group_list/');
  }
  async function addTeamData(params: any) {
    const data = await post('/system_mgmt/group/create_group/', params);
    return data;
  }
  async function updateGroup(params: any) {
    return await post('/system_mgmt/group/update_group/', params);
  }

  async function deleteTeam(params: any) {
    return await post('/system_mgmt/group/delete_groups/', params);
  }
  return {
    getTeamData,
    addTeamData,
    updateGroup,
    deleteTeam,
  };
};
