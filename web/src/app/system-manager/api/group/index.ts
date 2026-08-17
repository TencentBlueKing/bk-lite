import useApiClient from '@/utils/request';
import type {
  ArchivedGroupChildNode,
  ArchivedGroupKind,
  ArchivedGroupListPage,
  ArchivedGroupRoot,
} from '@/app/system-manager/types/archived-group';

const ARCHIVED_KINDS = new Set<ArchivedGroupKind>([
  'local',
  'synced_active_source',
  'synced_deleted_source',
]);

function isArchivedChildNode(value: unknown): value is ArchivedGroupChildNode {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const node = value as Record<string, unknown>;
  return (
    typeof node.id === 'number'
    && typeof node.name === 'string'
    && typeof node.parent_id === 'number'
    && (node.children === undefined || (Array.isArray(node.children) && node.children.every(isArchivedChildNode)))
  );
}

function isArchivedGroupRoot(value: unknown): value is ArchivedGroupRoot {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const node = value as Record<string, unknown>;
  return (
    isArchivedChildNode(value)
    && typeof node.kind === 'string'
    && ARCHIVED_KINDS.has(node.kind as ArchivedGroupKind)
    && typeof node.can_restore === 'boolean'
    && typeof node.can_permanently_delete === 'boolean'
  );
}

function parseArchivedListPage(data: unknown): ArchivedGroupListPage {
  if (!data || typeof data !== 'object') {
    return { items: [], count: 0, page: 1, page_size: 50 };
  }
  const payload = data as Record<string, unknown>;
  const rawItems = Array.isArray(payload.items) ? payload.items : [];
  const items = rawItems.filter(isArchivedGroupRoot);
  return {
    items,
    count: typeof payload.count === 'number' ? payload.count : items.length,
    page: typeof payload.page === 'number' ? payload.page : 1,
    page_size: typeof payload.page_size === 'number' ? payload.page_size : 50,
  };
}

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

  /** 语义已为软归档（后端 delete_groups → ArchiveService） */
  async function deleteTeam(params: { id: number }) {
    return await post('/system_mgmt/group/delete_groups/', params);
  }

  async function listArchivedGroups(params?: { page?: number; pageSize?: number }): Promise<ArchivedGroupListPage> {
    const data = await get('/system_mgmt/group/list_archived_groups/', {
      params: {
        page: params?.page ?? 1,
        page_size: params?.pageSize ?? 50,
      },
    });
    return parseArchivedListPage(data);
  }

  async function restoreArchivedGroup(params: { id: number }) {
    return await post('/system_mgmt/group/restore_archived_groups/', params);
  }

  async function permanentlyDeleteArchivedGroup(params: { id: number }) {
    return await post('/system_mgmt/group/permanently_delete_archived_groups/', params);
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
    listArchivedGroups,
    restoreArchivedGroup,
    permanentlyDeleteArchivedGroup,
    getGroupRoles,
    getGroupDetailWithRoles,
    batchGetGroupDetailWithRoles,
  };
};
