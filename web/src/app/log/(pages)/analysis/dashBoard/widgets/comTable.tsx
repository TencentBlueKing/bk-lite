import React, { useEffect, useState, useRef } from 'react';
import CustomTable from '@/components/custom-table';
import { TableDataItem } from '@/app/log/types';

interface ComTableProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const ComTable: React.FC<ComTableProps> = ({
  rawData,
  loading = false,
  config,
}) => {
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [scrollY, setScrollY] = useState<number>(300);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loading) {
      const data = (rawData || []).map((item: TableDataItem, index: number) => {
        return {
          id: index,
          ...item,
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

  return (
    <div ref={containerRef} className="h-full flex">
      <CustomTable
        className="w-full"
        loading={loading}
        columns={config?.columns || []}
        dataSource={tableData}
        rowKey="id"
        scroll={{ y: scrollY }}
        virtual
      />
    </div>
  );
};

export default ComTable;
