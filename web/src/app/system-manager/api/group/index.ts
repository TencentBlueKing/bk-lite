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
  async function updateGroup(params: { group_id: string | number; group_name: string; role_ids: number[]; allow_inherit_roles?: boolean }) {
    return await post('/system_mgmt/group/update_group/', params);
  }

  async function deleteTeam(params: any) {
    return await post('/system_mgmt/group/delete_groups/', params);
  }

  async function getGroupRoles(params: { group_ids: number[] }): Promise<{ id: number; name: string; app: string }[]> {
    return await post('/system_mgmt/role/get_groups_roles/', params);
  }

  async function getGroupDetailWithRoles(params: { group_id: number | string }): Promise<{
    group_id: number;
    group_name: string;
    allow_inherit_roles: boolean;
    own_role_ids: number[];
    inherited_role_ids: number[];
    inherited_role_source: string;
    inherited_role_source_map: Record<string, string>;
  }> {
    return await post('/system_mgmt/group/get_group_detail_with_roles/', params);
  }

  async function batchGetGroupDetailWithRoles(params: { group_ids: (number | string)[] }): Promise<{
    group_id: number;
    group_name: string;
    allow_inherit_roles: boolean;
    own_role_ids: number[];
    inherited_role_ids: number[];
    inherited_role_source: string;
    inherited_role_source_map: Record<string, string>;
  }[]> {
    return await post('/system_mgmt/group/batch_get_group_detail_with_roles/', params);
  }

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
