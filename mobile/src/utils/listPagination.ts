/** 列表未超过一页时不渲染 InfiniteScroll，避免首屏就出现「没有更多了」。 */
export function shouldShowListPagination(
  count: number | null,
  loadedCount: number,
  pageSize: number,
): boolean {
  return count === null ? loadedCount >= pageSize : count > pageSize;
}
