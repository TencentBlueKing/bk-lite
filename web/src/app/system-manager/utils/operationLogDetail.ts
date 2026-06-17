export function hasOperationDetail(row: { detail?: Record<string, any> | null }): boolean {
  return !!row.detail && typeof row.detail === 'object' && Object.keys(row.detail).length > 0;
}
