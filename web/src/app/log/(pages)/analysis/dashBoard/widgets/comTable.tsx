import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import CustomTable from '@/components/custom-table';
import { TableDataItem } from '@/app/log/types';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

const TIME_FIELD_KEYS = new Set([
  '_time',
  '@timestamp',
  'timestamp',
  'last_change_time',
  'last_time'
]);

const normalizeTimeColumn = (
  column: Record<string, unknown>,
  formatTime: (value: unknown) => string
) => {
  const dataIndex = String(column.dataIndex ?? '');
  const normalizedIndex = dataIndex === '@timestamp' ? '_time' : dataIndex;
  const isTimeField = TIME_FIELD_KEYS.has(dataIndex);

  if (!isTimeField) {
    return column;
  }

  return {
    ...column,
    dataIndex: normalizedIndex,
    key: column.key === dataIndex ? normalizedIndex : column.key,
    render: column.render ?? ((value: unknown) => formatTime(value))
  };
};

interface ComTableProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const ComTable: React.FC<ComTableProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const { convertToLocalizedTime } = useLocalizedTime();
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [scrollY, setScrollY] = useState<number>(300);
  const containerRef = useRef<HTMLDivElement>(null);

  const formatTime = useCallback((value: unknown) => {
    if (value === null || value === undefined || value === '') {
      return '--';
    }
    return convertToLocalizedTime(String(value), 'YYYY-MM-DD HH:mm:ss');
  }, [convertToLocalizedTime]);

  useEffect(() => {
    if (!loading) {
      const data = (rawData || []).map((item: TableDataItem, index: number) => {
        return {
          id: index,
          ...item
        };
      });
      setTableData(data);
    }
  }, [rawData, loading]);

  useEffect(() => {
    const updateScrollHeight = () => {
      if (containerRef.current) {
        const containerHeight = containerRef.current.clientHeight;
        // 减去表格头部高度 (大约 55px) 和一些边距
        const calculatedHeight = Math.max(20, containerHeight - 80);
        setScrollY(calculatedHeight);
      }
    };
    updateScrollHeight();
    // 监听窗口大小变化
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

  const columns = useMemo(() => {
    const configuredColumns = (config?.columns || []).map((column: Record<string, unknown>) =>
      normalizeTimeColumn(column, formatTime)
    );

    if (!config?.showIndex) {
      return configuredColumns;
    }

    return [
      {
        key: '__index__',
        title: '#',
        dataIndex: '__index__',
        align: 'center' as const,
        width: 72,
        render: (_: unknown, __: TableDataItem, index: number) => (
          <span className="inline-flex min-w-[32px] items-center justify-center rounded-full bg-[var(--color-fill-2)] px-2.5 py-1 text-xs font-semibold leading-none text-[var(--color-text-2)]">
            {index + 1}
          </span>
        )
      },
      ...configuredColumns
    ];
  }, [config?.columns, config?.showIndex, formatTime]);

  return (
    <div ref={containerRef} className="h-full flex">
      <CustomTable
        className="w-full"
        loading={loading}
        columns={columns}
        dataSource={tableData}
        rowKey="id"
        size="small"
        scroll={{ y: scrollY }}
        virtual
      />
    </div>
  );
};

export default ComTable;
