import React, { useEffect, useState, useRef } from 'react';
import { Tooltip } from 'antd';
import CustomTable from '@/components/custom-table';
import { TableDataItem } from '@/app/log/types';

interface MysqlDetailTableProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

const formatSeconds = (val: any): string => {
  const n = parseFloat(val);
  if (isNaN(n)) return '--';
  if (n === 0) return '0s';
  return `${n.toFixed(3)}s`;
};

const formatTime = (val: any): string => {
  if (!val) return '--';
  try {
    return new Date(val).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  } catch {
    return String(val);
  }
};

const extractSlowlogMetric = (
  msg: string,
  field: 'query_time' | 'lock_time' | 'rows_examined'
) => {
  if (!msg) return undefined;
  const match = msg.match(
    /Query_time:\s+([0-9.]+)\s+Lock_time:\s+([0-9.]+)\s+Rows_sent:\s+[0-9]+\s+Rows_examined:\s+([0-9]+)/
  );
  if (!match) return undefined;
  if (field === 'query_time') return match[1];
  if (field === 'lock_time') return match[2];
  return match[3];
};

const extractSlowlogUser = (msg: string) => {
  if (!msg) return undefined;
  const firstLine = msg.split('\n')[0] || '';
  const match = firstLine.match(/^# User@Host:\s+([^\[]+)\[/);
  return match?.[1]?.trim();
};

const extractSlowlogHost = (msg: string) => {
  if (!msg) return undefined;
  const firstLine = msg.split('\n')[0] || '';
  const match = firstLine.match(/@\s+([^\[]+)\s*\[/);
  return match?.[1]?.trim();
};

const extractErrorCode = (msg: string) => {
  if (!msg) return undefined;
  const firstLine = msg.split('\n').find((line) => line.trim()) || '';
  // 新格式: [MY-010931]
  const newFmt = firstLine.match(/\[MY-(\d+)\]/);
  if (newFmt) return newFmt[1];
  // 老格式: ERROR 1126 (HY000)
  const oldFmt = firstLine.match(/^\s*[A-Z]+\s+(\d+)\s+\(/i);
  return oldFmt?.[1];
};

// 慢查询明细列（event.dataset: mysql.slowlog）
const SLOWLOG_COLUMNS = [
  {
    key: '_time',
    title: '时间',
    dataIndex: '_time',
    width: 130,
    render: formatTime
  },
  {
    key: 'mysql.slowlog.query_time.sec',
    title: '耗时',
    dataIndex: 'mysql.slowlog.query_time.sec',
    align: 'right' as const,
    width: 80,
    render: (val: any, record: any) =>
      formatSeconds(val ?? extractSlowlogMetric(record?._msg, 'query_time'))
  },
  {
    key: 'mysql.slowlog.lock_time.sec',
    title: '锁时',
    dataIndex: 'mysql.slowlog.lock_time.sec',
    align: 'right' as const,
    width: 80,
    render: (val: any, record: any) => {
      const n = parseFloat(
        val ?? extractSlowlogMetric(record?._msg, 'lock_time') ?? ''
      );
      if (isNaN(n)) return '--';
      return (
        <span style={{ color: n > 0.1 ? 'var(--color-warning)' : undefined }}>
          {n.toFixed(3)}s
        </span>
      );
    }
  },
  {
    key: 'mysql.slowlog.rows_examined',
    title: '扫描行',
    dataIndex: 'mysql.slowlog.rows_examined',
    align: 'right' as const,
    width: 80,
    render: (val: any, record: any) => {
      const n = parseFloat(
        val ?? extractSlowlogMetric(record?._msg, 'rows_examined') ?? ''
      );
      if (isNaN(n)) return '--';
      const rounded = Math.round(n);
      return (
        <span
          style={{ color: rounded > 10000 ? 'var(--color-danger)' : undefined }}
        >
          {rounded.toLocaleString()}
        </span>
      );
    }
  },
  {
    key: 'mysql.slowlog.user',
    title: '用户',
    dataIndex: 'mysql.slowlog.user',
    width: 90,
    render: (val: any, record: any) =>
      val ||
      extractSlowlogUser(record?._msg) || (
        <span className="text-[var(--color-text-4)]">--</span>
      )
  },
  {
    key: 'mysql.slowlog.host',
    title: '来源主机',
    dataIndex: 'mysql.slowlog.host',
    width: 100,
    render: (val: any, record: any) => {
      const host = val || extractSlowlogHost(record?._msg);
      return host ? (
        <span className="text-xs">{host}</span>
      ) : (
        <span className="text-[var(--color-text-4)]">--</span>
      );
    }
  },
  {
    key: '_msg',
    title: 'SQL',
    dataIndex: '_msg',
    render: (val: string) => {
      if (!val) return '--';
      const lines = val
        .split('\n')
        .filter((l) => !l.startsWith('#') && l.trim());
      const sql = lines.join(' ').trim() || val;
      const preview = sql.length > 60 ? `${sql.slice(0, 60)}…` : sql;
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
  }
];

// 错误日志明细列（event.dataset: mysql.error）
const ERRORLOG_COLUMNS = [
  {
    key: '_time',
    title: '时间',
    dataIndex: '_time',
    width: 140,
    render: formatTime
  },
  {
    key: 'error.code',
    title: '错误码',
    dataIndex: 'error.code',
    width: 80,
    render: (val: any, record: any) => {
      const code = String(val || extractErrorCode(record?._msg) || '');
      if (!code) return <span className="text-[var(--color-text-4)]">--</span>;
      return <span className="font-mono text-xs">{code}</span>;
    }
  },
  {
    key: '_msg',
    title: '错误信息',
    dataIndex: '_msg',
    render: (val: string) => {
      if (!val) return '--';
      const preview = val.length > 120 ? `${val.slice(0, 120)}…` : val;
      return (
        <Tooltip
          title={
            <pre className="whitespace-pre-wrap text-xs max-w-[500px] max-h-[300px] overflow-auto">
              {val}
            </pre>
          }
          placement="topLeft"
        >
          <span className="cursor-pointer text-xs text-[var(--color-text-1)]">
            {preview}
          </span>
        </Tooltip>
      );
    }
  }
];

const MysqlDetailTable: React.FC<MysqlDetailTableProps> = ({
  rawData,
  loading = false,
  config
}) => {
  const [tableData, setTableData] = useState<TableDataItem[]>([]);
  const [scrollY, setScrollY] = useState<number>(300);
  const containerRef = useRef<HTMLDivElement>(null);

  // 通过 config.variant 区分慢查询明细 vs 错误日志明细
  const variant = config?.variant || 'slowlog';
  const columns = variant === 'errorlog' ? ERRORLOG_COLUMNS : SLOWLOG_COLUMNS;

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
        setScrollY(Math.max(20, containerRef.current.clientHeight - 80));
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
        columns={columns}
        dataSource={tableData}
        rowKey="id"
        size="small"
        scroll={{ x: 'max-content', y: scrollY }}
        virtual
      />
    </div>
  );
};

export default MysqlDetailTable;
