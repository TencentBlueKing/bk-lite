import React, { forwardRef } from 'react';
import { Spin } from 'antd';
import ChartEmptyState, {
  type ChartEmptyStateProps,
} from '@/components/chart-empty-state';

export interface ChartSurfaceProps {
  hasData: boolean;
  loading?: boolean;
  loadingContent?: React.ReactNode;
  containerClassName?: string;
  loadingClassName?: string;
  emptyClassName?: string;
  emptyStateProps?: ChartEmptyStateProps;
  children: React.ReactNode;
}

const ChartSurface = forwardRef<HTMLDivElement, ChartSurfaceProps>(
  (
    {
      hasData,
      loading = false,
      loadingContent,
      containerClassName = '',
      loadingClassName = 'flex h-full items-center justify-center',
      emptyClassName = '',
      emptyStateProps,
      children,
    },
    ref
  ) => {
    return (
      <div ref={ref} className={containerClassName}>
        {loading ? (
          <div className={loadingClassName}>
            {loadingContent || <Spin size="small" />}
          </div>
        ) : hasData ? (
          children
        ) : (
          <div className={emptyClassName}>
            <ChartEmptyState compact {...emptyStateProps} />
          </div>
        )}
      </div>
    );
  }
);

ChartSurface.displayName = 'ChartSurface';

export default ChartSurface;
