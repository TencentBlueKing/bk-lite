import { useEffect, useState, type RefObject } from 'react';

interface UseTableBodyScrollYOptions {
  containerRef: RefObject<HTMLDivElement | null>;
  hasPagination: boolean;
}

/**
 * 与 CustomTable size="small" 加回的高度相同：表头 47、分页 56。
 * widgetUiScale 已经用在大屏字号和单元格 padding 上，这里不能再乘一次。
 * 公共表格收到显式 scroll.y 时还会把表体抬到至少 160，所以运营分析表格
 * 不把这个返回值传给 CustomTable，只让它按父容器回填。
 */
export const resolveTableBodyScrollY = ({
  containerHeight,
  hasPagination,
}: {
  containerHeight: number;
  hasPagination: boolean;
}): number => {
  const headerHeight = 47;
  const paginationHeight = hasPagination ? 56 : 0;
  return Math.max(0, containerHeight - headerHeight - paginationHeight);
};

export const useTableBodyScrollY = ({
  containerRef,
  hasPagination,
}: UseTableBodyScrollYOptions): string | undefined => {
  const [tableScrollY, setTableScrollY] = useState<string>();

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const updateScrollY = () => {
      const nextHeight = resolveTableBodyScrollY({
        containerHeight: container.clientHeight,
        hasPagination,
      });
      setTableScrollY(`${nextHeight}px`);
    };

    updateScrollY();

    const resizeObserver = new ResizeObserver(updateScrollY);
    resizeObserver.observe(container);
    if (container.parentElement) {
      resizeObserver.observe(container.parentElement);
    }
    window.addEventListener('resize', updateScrollY);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', updateScrollY);
    };
  }, [containerRef, hasPagination]);

  return tableScrollY;
};
