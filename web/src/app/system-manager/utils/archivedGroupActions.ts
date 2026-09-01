/** 归档组织列表操作列展示：由后端 capability 决定，前端只映射文案形态。 */

export type ArchivedActionRow = {
  can_restore?: boolean;
  can_permanently_delete?: boolean;
};

export type ArchivedActionPresentation =
  | { type: 'empty' }
  | { type: 'sync_reconcile_reason' }
  | { type: 'buttons'; can_restore: boolean; can_permanently_delete: boolean };

export function getArchivedActionPresentation(row: ArchivedActionRow): ArchivedActionPresentation {
  const isRoot = typeof row.can_restore === 'boolean' || typeof row.can_permanently_delete === 'boolean';
  if (!isRoot) {
    return { type: 'empty' };
  }
  if (!row.can_restore && !row.can_permanently_delete) {
    return { type: 'sync_reconcile_reason' };
  }
  return {
    type: 'buttons',
    can_restore: Boolean(row.can_restore),
    can_permanently_delete: Boolean(row.can_permanently_delete),
  };
}
