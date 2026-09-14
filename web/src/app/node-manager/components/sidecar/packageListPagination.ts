export interface PackageListPagination {
  current: number;
  total: number;
  pageSize: number;
}

export interface PackageListPageResult {
  count: number;
  itemCount: number;
}

export const resolvePackageListPagination = (
  prev: PackageListPagination,
  { count, itemCount }: PackageListPageResult
): PackageListPagination => {
  const total = count || 0;
  const pageSize = prev.pageSize > 0 ? prev.pageSize : 1;
  const current =
    itemCount === 0 && total > 0 && prev.current > 1
      ? Math.max(1, Math.ceil(total / pageSize))
      : prev.current;

  return {
    ...prev,
    total,
    current,
  };
};
