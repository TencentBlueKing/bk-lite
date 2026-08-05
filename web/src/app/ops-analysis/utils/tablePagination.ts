interface DataSourceParamDeclaration {
  name?: string;
}

interface BuildTableQueryParamsInput {
  dataSourceParams?: DataSourceParamDeclaration[];
  queryParams?: Record<string, unknown>;
}

export const DEFAULT_TABLE_PAGE = 1;
export const DEFAULT_TABLE_PAGE_SIZE = 20;

export const supportsServerPagination = (
  params?: DataSourceParamDeclaration[],
): boolean => {
  const paramNames = new Set(
    (Array.isArray(params) ? params : [])
      .map((param) => param?.name)
      .filter((name): name is string => typeof name === 'string'),
  );

  return paramNames.has('page') && paramNames.has('page_size');
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

  return {
    ...nonPaginationParams,
    page: page ?? DEFAULT_TABLE_PAGE,
    page_size: pageSize ?? DEFAULT_TABLE_PAGE_SIZE,
  };
};
