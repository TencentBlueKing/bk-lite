import type { Key } from 'react';

export const DEFAULT_INST_PAGE_SIZE = 10;

export interface InstAssetRow {
  inst_uuid?: string;
}

export interface InstPaginationChange {
  currentPageSize: number;
  nextPage: number;
  nextPageSize: number;
}

export function resolveInstPaginationChange({
  currentPageSize,
  nextPage,
  nextPageSize,
}: InstPaginationChange) {
  const pageSize = nextPageSize || currentPageSize;
  return {
    page: pageSize === currentPageSize ? nextPage : 1,
    pageSize,
  };
}

export function resolveInstFetchModelId({
  isCommonSelectInstTask,
  instanceModelId,
  relateType,
}: {
  isCommonSelectInstTask: boolean;
  instanceModelId: string;
  collectionModelId: string;
  relateType: string;
}) {
  return isCommonSelectInstTask ? instanceModelId : relateType;
}

export function restoreInstDrawerSelection<T extends InstAssetRow>(
  selectedData: T[]
) {
  return {
    selectedKeys: selectedData
      .map((item) => item.inst_uuid)
      .filter((key): key is string => Boolean(key)),
    selectedRows: selectedData,
  };
}

export function mergeInstSelection<T extends InstAssetRow>({
  currentPageRows,
  selectedRowKeys,
  previousSelectedRows,
}: {
  currentPageRows: T[];
  selectedRowKeys: Key[];
  previousSelectedRows: T[];
}): T[] {
  const selectedKeySet = new Set(selectedRowKeys.map(String));
  const currentPageIds = new Set(
    currentPageRows
      .map((row) => row.inst_uuid)
      .filter((id): id is string => Boolean(id))
  );
  const nextById = new Map<string, T>();

  previousSelectedRows.forEach((row) => {
    if (row.inst_uuid && selectedKeySet.has(String(row.inst_uuid))) {
      nextById.set(String(row.inst_uuid), row);
    }
  });

  currentPageIds.forEach((id) => {
    if (!selectedKeySet.has(id)) {
      nextById.delete(id);
    }
  });

  currentPageRows.forEach((row) => {
    if (row.inst_uuid && selectedKeySet.has(String(row.inst_uuid))) {
      nextById.set(String(row.inst_uuid), row);
    }
  });

  return selectedRowKeys
    .map((key) => nextById.get(String(key)))
    .filter((row): row is T => Boolean(row));
}
