import { useEffect, useState, type RefObject } from 'react';

interface UseTableBodyScrollYOptions {
  containerRef: RefObject<HTMLDivElement | null>;
  hasPagination: boolean;
  scale?: number;
}

export const resolveTableBodyScrollY = ({
  containerHeight,
  hasPagination,
  scale = 1,
}: {
  containerHeight: number;
  hasPagination: boolean;
  scale?: number;
}): number => {
  const headerHeight = Math.round(43 * scale);
  const paginationHeight = hasPagination ? Math.round(56 * scale) : 0;
  const minBodyHeight = Math.round(120 * scale);

  return Math.max(
    containerHeight - headerHeight - paginationHeight,
    minBodyHeight,
  );
};

export const useTableBodyScrollY = ({
  containerRef,
  hasPagination,
  scale = 1,
}: UseTableBodyScrollYOptions): string | undefined => {
  const [tableScrollY, setTableScrollY] = useState<string>();

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const updateScrollY = () => {
      const nextHeight = resolveTableBodyScrollY({
        containerHeight: container.clientHeight,
        hasPagination,
        scale,
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
  }, [containerRef, hasPagination, scale]);

  return tableScrollY;
};
