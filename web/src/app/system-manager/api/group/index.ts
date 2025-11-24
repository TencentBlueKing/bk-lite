import useApiClient from '@/utils/request';
export const useGroupApi = () => {
  const { get, post } = useApiClient();
  async function getTeamData() {
    return await get('/system_mgmt/group/search_group_list/');
  }
  async function addTeamData(params: any) {
    const data = await post('/system_mgmt/group/create_group/', params);
    return data;
  }
  async function updateGroup(params: { group_id: string | number; group_name: string; role_ids: number[] }) {
    return await post('/system_mgmt/group/update_group/', params);
  }

  async function deleteTeam(params: any) {
    return await post('/system_mgmt/group/delete_groups/', params);
  }

  async function getGroupRoles(params: { group_ids: number[] }): Promise<{ id: number; name: string; app: string }[]> {
    return await post('/system_mgmt/role/get_groups_roles/', params);
  }

  return {
    getTeamData,
    addTeamData,
    updateGroup,
    deleteTeam,
    getGroupRoles
  };
};
