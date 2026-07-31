import type { ChartData } from '@/app/monitor/types';
import type { InterfaceTableItem } from '@/app/monitor/types/view';

interface LazyMetricItemMemoProps {
  item: {
    id: number;
    viewData?: ChartData[] | InterfaceTableItem[];
    seriesBudget?: {
      truncated: boolean;
      limit: number;
      applied?: boolean;
    };
  };
  xAxisDomain?: [number, number];
  isLoading: boolean;
  resetKey?: number;
  isLoaded: boolean;
  isCancelled: boolean;
  isInViewport: boolean;
}

export const areLazyMetricItemPropsEqual = (
  prevProps: LazyMetricItemMemoProps,
  nextProps: LazyMetricItemMemoProps
): boolean => (
  prevProps.item.id === nextProps.item.id &&
  prevProps.item.viewData === nextProps.item.viewData &&
  prevProps.item.seriesBudget?.truncated === nextProps.item.seriesBudget?.truncated &&
  prevProps.item.seriesBudget?.limit === nextProps.item.seriesBudget?.limit &&
  prevProps.xAxisDomain?.[0] === nextProps.xAxisDomain?.[0] &&
  prevProps.xAxisDomain?.[1] === nextProps.xAxisDomain?.[1] &&
  prevProps.isLoading === nextProps.isLoading &&
  prevProps.resetKey === nextProps.resetKey &&
  prevProps.isLoaded === nextProps.isLoaded &&
  prevProps.isCancelled === nextProps.isCancelled &&
  prevProps.isInViewport === nextProps.isInViewport
);
