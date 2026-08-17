/** 归档组织类型（独立于正常 Group 树类型，勿混用） */

export type ArchivedGroupKind =
  | 'local'
  | 'synced_active_source'
  | 'synced_deleted_source';

export interface ArchivedGroupChildNode {
  id: number;
  name: string;
  parent_id: number;
  children: ArchivedGroupChildNode[];
}

export interface ArchivedGroupRoot {
  id: number;
  name: string;
  parent_id: number;
  kind: ArchivedGroupKind;
  can_restore: boolean;
  can_permanently_delete: boolean;
  children: ArchivedGroupChildNode[];
  children_truncated?: boolean;
}

export interface ArchivedGroupListPage {
  items: ArchivedGroupRoot[];
  count: number;
  page: number;
  page_size: number;
}
