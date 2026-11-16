import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  parseTableLikeData,
  type TableLikePaginationState,
} from '@/app/ops-analysis/utils/tableLikeData';
import {
  readExplicitPageNumber,
  readExplicitPagePair,
  supportsServerPagination,
} from '@/app/ops-analysis/utils/tablePagination';

interface NamedParam {
  name?: string;
  value?: unknown;
}

const savedPageKey = (params?: NamedParam[]) => {
  const pair = readExplicitPagePair(params);
  return `${pair.page ?? ''}:${pair.page_size ?? ''}`;
};

const readSavedPageState = (params?: NamedParam[]): TableLikePaginationState => {
  const pair = readExplicitPagePair(params);
  if (pair.page === undefined || pair.page_size === undefined) return {};
  return { current: pair.page, pageSize: pair.page_size };
};

export function useTableServerQuery<RecordType extends Record<string, any>>({
  rawData,
  sourceParams,
  savedParams,
  onQueryChange,
  additionalQuery,
}: {
  rawData: unknown;
  sourceParams?: NamedParam[];
  savedParams?: NamedParam[];
  onQueryChange?: (params: Record<string, any>) => void;
  additionalQuery?: Record<string, unknown>;
}) {
  const supportsPaginationParams = useMemo(
    () => supportsServerPagination(sourceParams),
    [sourceParams],
  );
  const savedKey = savedPageKey(savedParams);
  const savedParamsRef = useRef(savedParams);
  savedParamsRef.current = savedParams;
  const [queryPagination, setQueryPagination] = useState<TableLikePaginationState>(
    () => readSavedPageState(savedParams),
  );

  useEffect(() => {
    const next = readSavedPageState(savedParamsRef.current);
    setQueryPagination((prev) => (
      prev.current === next.current && prev.pageSize === next.pageSize ? prev : next
    ));
  }, [savedKey]);

  const parsed = useMemo(
    () => parseTableLikeData<RecordType>(rawData, queryPagination, supportsPaginationParams),
    [rawData, queryPagination, supportsPaginationParams],
  );
  const paginationKey = `${queryPagination.current ?? ''}:${queryPagination.pageSize ?? ''}`;
  const seenDataRef = useRef(rawData);
  const paginationAtDataRef = useRef(paginationKey);
  // 分页状态先变、结果还是上一份时，不用上一份的回显页码冒充这次请求。
  if (seenDataRef.current !== rawData) {
    seenDataRef.current = rawData;
    paginationAtDataRef.current = paginationKey;
  }
  const dataMatchesRequest = paginationAtDataRef.current === paginationKey;
  const requestPaged = queryPagination.current !== undefined
    && queryPagination.pageSize !== undefined;
  const selfPaged = parsed.selfPaged && dataMatchesRequest;
  const isPaginated = requestPaged ? parsed.isPaginated : selfPaged;

  const extraKey = JSON.stringify(additionalQuery ?? {});
  const extraRef = useRef(additionalQuery);
  extraRef.current = additionalQuery;

  useEffect(() => {
    if (!onQueryChange) return;
    const queryParams: Record<string, unknown> = { ...(extraRef.current ?? {}) };
    if (
      supportsPaginationParams
      && queryPagination.current !== undefined
      && queryPagination.pageSize !== undefined
    ) {
      queryParams.page = queryPagination.current;
      queryParams.page_size = queryPagination.pageSize;
    }
    onQueryChange(queryParams);
  }, [
    extraKey,
    onQueryChange,
    queryPagination.current,
    queryPagination.pageSize,
    supportsPaginationParams,
  ]);

  const handleTableChange = useCallback((pageConfig: { current?: number; pageSize?: number }) => {
    const current = readExplicitPageNumber(pageConfig?.current);
    const pageSize = readExplicitPageNumber(pageConfig?.pageSize);
    if (current === undefined || pageSize === undefined) return;
    setQueryPagination({ current, pageSize });
  }, []);

  const resetToFirstPage = useCallback(() => {
    setQueryPagination((prev) => {
      if (prev.current === undefined || prev.pageSize === undefined || prev.current === 1) {
        return prev;
      }
      return { ...prev, current: 1 };
    });
  }, []);

  return {
    rows: parsed.rows,
    pagination: parsed.pagination,
    isPaginated,
    selfPaged,
    handleTableChange,
    resetToFirstPage,
  };
}
