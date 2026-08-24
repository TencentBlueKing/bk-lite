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
  supportsPagination = false,
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
    const response = rawData as Record<string, unknown>;
    const items = response.items as RecordType[];
    const total = Number(response.count);
    const hasValidTotal =
      response.count !== undefined &&
      response.count !== null &&
      response.count !== '' &&
      Number.isFinite(total) &&
      total >= 0;
    return {
      rows: items,
      pagination: {
        current: queryPagination.current,
        pageSize: queryPagination.pageSize,
        total: hasValidTotal ? total : items.length,
      },
      isPaginated: supportsPagination && hasValidTotal,
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

interface TableLikeColumnConfigItem {
  key: string;
  title: string;
  visible: boolean;
  order: number;
}

interface ResolveTableLikeColumnsInput<
  RecordType extends Record<string, any>,
  ColumnType extends TableLikeColumnConfigItem,
> {
  configuredColumns?: ColumnType[];
  schemaFields?: ResponseFieldDefinition[];
  rows: RecordType[];
}

export function resolveTableLikeColumns<
  RecordType extends Record<string, any>,
  ColumnType extends TableLikeColumnConfigItem = TableColumnConfigItem,
>({
  configuredColumns = [],
  schemaFields = [],
  rows,
}: ResolveTableLikeColumnsInput<RecordType, ColumnType>): ColumnType[] {
  if (configuredColumns.length > 0) {
    return [...configuredColumns].sort((a, b) => a.order - b.order);
  }

  if (schemaFields.length > 0) {
    return schemaFields.map(
      (field, index) =>
        ({
          key: field.key,
          title: field.title || field.key,
          visible: true,
          order: index,
        }) as ColumnType,
    );
  }

  if (rows.length > 0) {
    return Object.keys(rows[0]).map(
      (key, index) =>
        ({
          key,
          title: key,
          visible: true,
          order: index,
        }) as ColumnType,
    );
  }

  return [];
}
