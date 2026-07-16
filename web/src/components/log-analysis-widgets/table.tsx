import React, { useEffect, useRef, useState } from 'react';
import type { TableDataItem } from '@/components/log-analysis-widgets/types';
import CustomTable from '@/components/custom-table';

export interface LogAnalysisTableProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const LogAnalysisTable: React.FC<LogAnalysisTableProps> = ({
  rawData,
  loading = false,
  config,
}) => {
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [scrollY, setScrollY] = useState<number>(300);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loading) {
      const data = (rawData || []).map((item: TableDataItem, index: number) => ({
        id: index,
        ...item,
      }));
      setTableData(data);
    }
  }, [loading, rawData]);

  useEffect(() => {
    const updateScrollHeight = () => {
      if (containerRef.current) {
        const containerHeight = containerRef.current.clientHeight;
        const calculatedHeight = Math.max(20, containerHeight - 80);
        setScrollY(calculatedHeight);
      }
    };

    updateScrollHeight();

    const resizeObserver = new ResizeObserver(() => {
      updateScrollHeight();
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  const columns = config?.showIndex
    ? [
      {
        key: '__index__',
        title: '#',
        dataIndex: '__index__',
        align: 'center' as const,
        width: config?.indexWidth || 72,
        render: (_: unknown, __: TableDataItem, index: number) => (
            <span className="inline-flex min-w-[32px] items-center justify-center rounded-full bg-[var(--color-fill-2)] px-2.5 py-1 text-xs font-semibold leading-none text-[var(--color-text-2)]">
              {index + 1}
            </span>
        ),
      },
      ...(config?.columns || []),
    ]
    : config?.columns || [];

  return (
    <div ref={containerRef} className="flex h-full">
      <CustomTable
        className="w-full"
        loading={loading}
        columns={columns}
        dataSource={tableData}
        rowKey="id"
        size="small"
        scroll={{
          y: scrollY,
          ...(config?.scrollX ? { x: config.scrollX } : {}),
        }}
        virtual
        expandable={config?.expandable}
      />
    </div>
  );
};

export default LogAnalysisTable;
