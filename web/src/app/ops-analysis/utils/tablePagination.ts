interface DataSourceParamDeclaration {
  name?: string;
  type?: string;
  value?: unknown;
}

interface BuildTableQueryParamsInput {
  dataSourceParams?: DataSourceParamDeclaration[];
  queryParams?: Record<string, unknown>;
}

export const readExplicitPageNumber = (value: unknown): number | undefined => {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) return undefined;
    value = Number(trimmed);
  }
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 1) {
    return undefined;
  }
  return value;
};

export const readExplicitPagePair = (
  params?: DataSourceParamDeclaration[],
): Record<string, number> => {
  const page = readExplicitPageNumber(
    params?.find((param) => param?.name === 'page')?.value,
  );
  const pageSize = readExplicitPageNumber(
    params?.find((param) => param?.name === 'page_size')?.value,
  );
  if (page === undefined || pageSize === undefined) return {};
  return { page, page_size: pageSize };
};

export const supportsServerPagination = (
  params?: DataSourceParamDeclaration[],
): boolean => {
  const page = (Array.isArray(params) ? params : []).find((param) => param?.name === 'page');
  const pageSize = (Array.isArray(params) ? params : []).find((param) => param?.name === 'page_size');
  return page?.type === 'number' && pageSize?.type === 'number';
};

export const buildTableQueryParams = ({
  dataSourceParams,
  queryParams = {},
}: BuildTableQueryParamsInput): Record<string, unknown> => {
  const {
    page,
    page_size: pageSize,
    ...nonPaginationParams
  } = queryParams;

  if (!supportsServerPagination(dataSourceParams)) {
    return nonPaginationParams;
  }

  const explicitPage = readExplicitPageNumber(page);
  const explicitPageSize = readExplicitPageNumber(pageSize);
  return {
    ...nonPaginationParams,
    ...(explicitPage !== undefined ? { page: explicitPage } : {}),
    ...(explicitPageSize !== undefined ? { page_size: explicitPageSize } : {}),
  };
};

export const serializeTableQueryKey = (
  queryParams: Record<string, unknown> = {},
  dataSourceParams?: DataSourceParamDeclaration[],
): string =>
  JSON.stringify(buildTableQueryParams({ dataSourceParams, queryParams }));

export const areTableQueryParamsEquivalent = (
  left: Record<string, unknown> = {},
  right: Record<string, unknown> = {},
  dataSourceParams?: DataSourceParamDeclaration[],
): boolean =>
  serializeTableQueryKey(left, dataSourceParams)
  === serializeTableQueryKey(right, dataSourceParams);
