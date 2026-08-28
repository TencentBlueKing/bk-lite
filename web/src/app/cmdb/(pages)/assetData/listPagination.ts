export interface ListPaginationState {
  current?: number;
}

export const resetListPaginationToFirstPage = <T extends ListPaginationState>(
  pagination: T
): T => {
  if ((pagination.current ?? 1) <= 1) {
    return pagination;
  }
  return { ...pagination, current: 1 };
};
