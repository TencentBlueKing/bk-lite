import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import type { TableColumnConfigItem } from '@/app/ops-analysis/types/dashBoard';

export interface TableLikePaginationState {
  current: number;
  pageSize: number;
}

export interface TableLikePagination extends TableLikePaginationState {
  total: number;
}

export interface TableLikeParseResult<RecordType extends Record<string, any>> {
  rows: RecordType[];
  pagination: TableLikePagination;
  isPaginated: boolean;
}

const isRecordArray = (value: unknown): value is Record<string, any>[] =>
  Array.isArray(value);

export const parseTableLikeData = <RecordType extends Record<string, any>>(
  rawData: unknown,
  queryPagination: TableLikePaginationState,
): TableLikeParseResult<RecordType> => {
  const emptyPagination = {
    current: queryPagination.current,
    pageSize: queryPagination.pageSize,
    total: 0,
  };

  if (!rawData) {
    return {
      rows: [],
      pagination: emptyPagination,
      isPaginated: false,
    };
  }

  if (
    typeof rawData === 'object' &&
    !Array.isArray(rawData) &&
    Array.isArray((rawData as Record<string, unknown>).items)
  ) {
    const items = (rawData as Record<string, unknown>).items as RecordType[];
    return {
      rows: items,
      pagination: {
        current: queryPagination.current,
        pageSize: queryPagination.pageSize,
        total: Number((rawData as Record<string, unknown>).count) || items.length,
      },
      isPaginated: true,
    };
  }

  if (isRecordArray(rawData)) {
    return {
      rows: rawData as RecordType[],
      pagination: {
        current: queryPagination.current,
        pageSize: queryPagination.pageSize,
        total: rawData.length,
      },
      isPaginated: false,
    };
  }

  return {
    rows: [],
    pagination: emptyPagination,
    isPaginated: false,
  };
};

export const toDisplayFieldValue = (value: unknown): string => {
  if (value === null || value === undefined) {
    return '--';
  }

  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }

  return String(value);
};

export const getRecordEntries = (record: Record<string, unknown>) =>
  Object.entries(record).map(([key, value]) => ({
    key,
    value: toDisplayFieldValue(value),
  }));

interface ResolveTableLikeColumnsInput<RecordType extends Record<string, any>> {
  configuredColumns?: TableColumnConfigItem[];
  schemaFields?: ResponseFieldDefinition[];
  rows: RecordType[];
}

export const resolveTableLikeColumns = <RecordType extends Record<string, any>>({
  configuredColumns = [],
  schemaFields = [],
  rows,
}: ResolveTableLikeColumnsInput<RecordType>): TableColumnConfigItem[] => {
  if (configuredColumns.length > 0) {
    return [...configuredColumns].sort((a, b) => a.order - b.order);
  }

  if (schemaFields.length > 0) {
    return schemaFields.map((field, index) => ({
      key: field.key,
      title: field.title || field.key,
      visible: true,
      order: index,
    }));
  }

  if (rows.length > 0) {
    return Object.keys(rows[0]).map((key, index) => ({
      key,
      title: key,
      visible: true,
      order: index,
    }));
  }

  return [];
};