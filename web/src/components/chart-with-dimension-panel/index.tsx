import React, { forwardRef } from 'react';
import ChartSurface from '@/components/chart-surface';
import ChartDimensionFilter, {
  type ChartDimensionFilterProps,
} from '@/components/chart-dimension-filter';
import ChartDimensionTable, {
  type ChartDimensionTableProps,
} from '@/components/chart-dimension-table';

export interface ChartWithDimensionPanelProps {
  hasData: boolean;
  chart: React.ReactNode;
  emptyClassName?: string;
  containerClassName?: string;
  filterProps?: ChartDimensionFilterProps;
  tableProps?: ChartDimensionTableProps;
}

const ChartWithDimensionPanel = forwardRef<
  HTMLDivElement,
  ChartWithDimensionPanelProps
>(
  (
    {
      hasData,
      chart,
      emptyClassName,
      containerClassName,
      filterProps,
      tableProps,
    },
    ref
  ) => {
    const hasSidePanel = Boolean(filterProps || tableProps);
    const resolvedContainerClassName =
      containerClassName ||
      `flex h-full w-full ${hasSidePanel ? 'flex-row' : 'flex-col'}`;

    return (
      <ChartSurface
        ref={ref}
        hasData={hasData}
        containerClassName={resolvedContainerClassName}
        emptyClassName={emptyClassName}
      >
        <>
          {chart}
          {filterProps ? <ChartDimensionFilter {...filterProps} /> : null}
          {tableProps ? <ChartDimensionTable {...tableProps} /> : null}
        </>
      </ChartSurface>
    );
  }
);

ChartWithDimensionPanel.displayName = 'ChartWithDimensionPanel';

export default ChartWithDimensionPanel;
