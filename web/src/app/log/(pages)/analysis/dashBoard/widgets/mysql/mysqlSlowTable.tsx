import React, { useEffect, useState, useRef } from 'react';
import { Tooltip } from 'antd';
import CustomTable from '@/components/custom-table';
import { TableDataItem } from '@/app/log/types';

interface MysqlSlowTableProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

// 格式化秒数，保留 3 位小数
const formatSeconds = (val: any): string => {
  const n = parseFloat(val);
  if (isNaN(n)) return '--';
  return `${n.toFixed(3)}s`;
};

// 格式化行数，整数显示
const formatRows = (val: any): string => {
  const n = parseFloat(val);
  if (isNaN(n)) return '--';
  return Math.round(n).toLocaleString();
};

const extractRowsExamined = (msg: string): string | undefined => {
  if (!msg) return undefined;
  const match = msg.match(/Rows_examined:\s+([0-9]+)/);
  return match?.[1];
};

const SLOW_TABLE_COLUMNS = [
  {
    key: '__index__',
    title: '#',
    dataIndex: '__index__',
    align: 'center' as const,
    width: 48,
    render: (_: unknown, __: TableDataItem, index: number) => (
      <span className="inline-flex min-w-[28px] items-center justify-center rounded-full bg-[var(--color-fill-2)] px-2 py-0.5 text-xs font-semibold leading-none text-[var(--color-text-2)]">
        {index + 1}
      </span>
    )
  },
  {
    key: '_msg',
    title: 'SQL 预览',
    dataIndex: '_msg',
    ellipsis: false,
    render: (val: string) => {
      if (!val) return '--';
      // 从慢查询原始内容中提取 SQL 语句部分（# 注释行之后）
      const lines = val
        .split('\n')
        .filter((l) => !l.startsWith('#') && l.trim());
      const sql = lines.join(' ').trim() || val;
      const preview = sql.length > 80 ? `${sql.slice(0, 80)}…` : sql;
      return (
        <Tooltip
          title={
            <pre className="whitespace-pre-wrap text-xs max-w-[500px] max-h-[300px] overflow-auto">
              {sql}
            </pre>
          }
          placement="topLeft"
        >
          <span className="cursor-pointer font-mono text-xs text-[var(--color-text-1)]">
            {preview}
          </span>
        </Tooltip>
      );
    }
  },
  {
    key: 'exec_count',
    title: '执行次数',
    dataIndex: 'exec_count',
    align: 'right' as const,
    width: 90,
    render: (val: any) => {
      const n = parseFloat(val);
      return isNaN(n) ? '--' : Math.round(n).toLocaleString();
    }
  },
  {
    key: 'avg_time',
    title: '平均耗时',
    dataIndex: 'avg_time',
    align: 'right' as const,
    width: 90,
    render: formatSeconds
  },
  {
    key: 'max_time',
    title: '最大耗时',
    dataIndex: 'max_time',
    align: 'right' as const,
    width: 90,
    render: formatSeconds
  },
  {
    key: 'avg_rows',
    title: '均扫描行',
    dataIndex: 'avg_rows',
    align: 'right' as const,
    width: 90,
    render: (val: any, record: TableDataItem) =>
      formatRows(val ?? extractRowsExamined(String(record?._msg || '')))
  }
];

const MysqlSlowTable: React.FC<MysqlSlowTableProps> = ({
  rawData,
  loading = false
}) => {
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [scrollY, setScrollY] = useState<number>(300);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loading) {
      const data = (rawData || []).map(
        (item: TableDataItem, index: number) => ({
          id: index,
          ...item
        })
      );
      setTableData(data);
    }
  }, [rawData, loading]);

  useEffect(() => {
    const updateScrollHeight = () => {
      if (containerRef.current) {
        const containerHeight = containerRef.current.clientHeight;
        setScrollY(Math.max(20, containerHeight - 80));
      }
    };
    updateScrollHeight();
    const ro = new ResizeObserver(updateScrollHeight);
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={containerRef} className="h-full flex">
      <CustomTable
        className="w-full"
        loading={loading}
        columns={SLOW_TABLE_COLUMNS}
        dataSource={tableData}
        rowKey="id"
        size="small"
        scroll={{ y: scrollY }}
        virtual
      />
    </div>
  );
};

export default MysqlSlowTable;
