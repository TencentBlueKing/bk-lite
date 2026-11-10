import { useCallback, useLayoutEffect, useState } from 'react';

interface UseTableBodyScrollYOptions {
  hasPagination: boolean;
}

/**
 * 表体高度是槽位里量到的像素，减去当时的表头和分页块。
 * small 表头约 39、middle 约 47、放大后可以到 57；分页折行后会高于 56。
 * 这些都取元素的 offsetHeight，不再写死。
 * widgetUiScale 已经用在大屏字号和单元格 padding 上，这里不能再乘一次。
 * 返回值是数字，交给 CustomTable 的 scroll.y。数字不再被抬到 160。
 * 无分页时省略 y 会让表体按内容撑高，再被卡片 overflow:hidden 裁掉且无法滚动。
 */
export const resolveTableBodyScrollY = ({
  containerHeight,
  headerHeight,
  paginationHeight,
}: {
  containerHeight: number;
  headerHeight: number;
  paginationHeight: number;
}): number => Math.max(0, containerHeight - headerHeight - paginationHeight);

const readChromeHeight = (container: HTMLElement, hasPagination: boolean) => {
  const headerBlock = container.querySelector<HTMLElement>('.ant-table-header');
  const headerRow = container.querySelector<HTMLElement>('.ant-table-thead');
  const headerHeight = headerBlock?.offsetHeight || headerRow?.offsetHeight || 0;
  if (!hasPagination) {
    return { headerHeight, paginationHeight: 0 };
  }
  const pagination = container.querySelector<HTMLElement>('.ant-pagination');
  const paginationBlock = pagination?.parentElement instanceof HTMLElement
    && container.contains(pagination.parentElement)
    ? pagination.parentElement
    : pagination;
  const paginationHeight = Math.max(
    pagination?.offsetHeight ?? 0,
    paginationBlock?.offsetHeight ?? 0,
  );
  return { headerHeight, paginationHeight };
};

export const useTableBodyScrollY = ({
  hasPagination,
}: UseTableBodyScrollYOptions): {
  slotRef: (node: HTMLDivElement | null) => void;
  tableScrollY: number | undefined;
} => {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const [tableScrollY, setTableScrollY] = useState<number>();
  const slotRef = useCallback((node: HTMLDivElement | null) => {
    setContainer(node);
  }, []);

  useLayoutEffect(() => {
    if (!container) return;

    const updateScrollY = () => {
      if (container.clientHeight <= 0) return;
      const { headerHeight, paginationHeight } = readChromeHeight(container, hasPagination);
      if (headerHeight <= 0 && !container.querySelector('.ant-table')) return;
      const nextHeight = resolveTableBodyScrollY({
        containerHeight: container.clientHeight,
        headerHeight,
        paginationHeight,
      });
      setTableScrollY((previous) => (previous === nextHeight ? previous : nextHeight));
    };

    updateScrollY();

    let resizeObserver: ResizeObserver | undefined;
    const observed = new Set<Element>();
    const observe = (node: Element | null | undefined) => {
      if (!node || !resizeObserver || observed.has(node)) return;
      observed.add(node);
      resizeObserver.observe(node);
    };
    const observeChrome = () => {
      observe(container.querySelector('.ant-table-header'));
      observe(container.querySelector('.ant-table-thead'));
      observe(container.querySelector('.ant-pagination'));
      observe(container.querySelector('.ant-pagination')?.parentElement);
    };

    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(updateScrollY);
      observe(container);
      observe(container.parentElement);
      observeChrome();
    }
    const mutationObserver = typeof MutationObserver === 'undefined'
      ? undefined
      : new MutationObserver(() => {
        observeChrome();
        updateScrollY();
      });
    mutationObserver?.observe(container, { childList: true, subtree: true });
    window.addEventListener('resize', updateScrollY);

    return () => {
      resizeObserver?.disconnect();
      mutationObserver?.disconnect();
      window.removeEventListener('resize', updateScrollY);
    };
  }, [container, hasPagination]);

  return { slotRef, tableScrollY };
};
