import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import type { TableColumnConfigItem } from '@/app/ops-analysis/types/dashBoard';
import { readExplicitPageNumber } from '@/app/ops-analysis/utils/tablePagination';

export interface TableLikePaginationState {
  current?: number;
  pageSize?: number;
}

export interface TableLikePagination {
  current: number;
  pageSize: number;
  total: number;
}

export interface TableLikeParseResult<RecordType extends Record<string, any>> {
  rows: RecordType[];
  pagination: TableLikePagination;
  isPaginated: boolean;
  selfPaged: boolean;
}

const isRecordArray = (value: unknown): value is Record<string, any>[] =>
  Array.isArray(value);

export const parseTableLikeData = <RecordType extends Record<string, any>>(
  rawData: unknown,
  queryPagination: TableLikePaginationState,
  supportsPagination = false,
): TableLikeParseResult<RecordType> => {
  const requestPage = readExplicitPageNumber(queryPagination.current);
  const requestPageSize = readExplicitPageNumber(queryPagination.pageSize);
  const emptyPagination = {
    current: requestPage ?? 1,
    pageSize: requestPageSize ?? 1,
    total: 0,
  };

  if (!rawData) {
    return {
      rows: [],
      pagination: emptyPagination,
      isPaginated: false,
      selfPaged: false,
    };
  }

  if (
    typeof rawData === 'object' &&
    !Array.isArray(rawData) &&
    Array.isArray((rawData as Record<string, unknown>).items)
  ) {
    const response = rawData as Record<string, unknown>;
    const items = response.items as RecordType[];
    const rawTotal = response.count !== undefined && response.count !== null && response.count !== ''
      ? response.count
      : response.total;
    const total = Number(rawTotal);
    const hasValidTotal =
      rawTotal !== undefined &&
      rawTotal !== null &&
      rawTotal !== '' &&
      Number.isFinite(total) &&
      total >= 0;
    const echoPage = readExplicitPageNumber(response.page);
    const echoPageSize = readExplicitPageNumber(response.page_size);
    const requestPaged = requestPage !== undefined && requestPageSize !== undefined;
    const selfPaged = supportsPagination
      && !requestPaged
      && echoPage !== undefined
      && echoPageSize !== undefined
      && hasValidTotal
      && total > items.length;
    return {
      rows: items,
      pagination: {
        current: (selfPaged ? echoPage : requestPage) ?? 1,
        pageSize: (selfPaged ? echoPageSize : requestPageSize) ?? Math.max(items.length, 1),
        total: hasValidTotal ? total : items.length,
      },
      isPaginated: supportsPagination && hasValidTotal && (requestPaged || selfPaged),
      selfPaged,
    };
  }

  if (isRecordArray(rawData)) {
    return {
      rows: rawData as RecordType[],
      pagination: {
        current: requestPage ?? 1,
        pageSize: requestPageSize ?? Math.max(rawData.length, 1),
        total: rawData.length,
      },
      isPaginated: false,
      selfPaged: false,
    };
  }

  return {
    rows: [],
    pagination: emptyPagination,
    isPaginated: false,
    selfPaged: false,
  };
};

export const isSelfPagedTablePayload = (rawData: unknown): boolean =>
  parseTableLikeData(rawData, {}, true).selfPaged;

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

  const tableSchema = schemaFields;
  if (tableSchema.length > 0) {
    return tableSchema.map(
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
