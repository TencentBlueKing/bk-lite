import React, { useEffect, useState, useRef } from 'react';
import { Tooltip } from 'antd';
import CustomTable from '@/components/custom-table';
import { TableDataItem } from '@/app/log/types';

interface RedisLogTableProps {
  rawData: any;
  loading?: boolean;
}

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

// 从 _msg 推断事件类型及颜色
const detectEventType = (msg: string): { label: string; color: string } => {
  if (!msg) return { label: '其他', color: 'default' };
  const upper = msg.toUpperCase();
  if (
    upper.startsWith('ERR') ||
    upper.startsWith('WRONGTYPE') ||
    upper.startsWith('FATAL')
  ) {
    return { label: 'ERR 错误', color: 'error' };
  }
  if (upper.startsWith('WARNING') || upper.startsWith('WARN')) {
    return { label: 'WARNING', color: 'warning' };
  }
  if (upper.startsWith('---[')) {
    // case= 格式：集群状态事件
    const caseMatch = msg.match(/case=([^\s,]+)/);
    if (caseMatch) return { label: `集群: ${caseMatch[1]}`, color: 'purple' };
    return { label: '状态事件', color: 'blue' };
  }
  if (/\bsave[d]?\b|\bRDB\b|\bAOF\b/i.test(msg)) {
    return { label: '持久化', color: 'green' };
  }
  if (/\breplica\b|\bmaster\b|\bsync\b/i.test(msg)) {
    return { label: '主从复制', color: 'cyan' };
  }
  if (/\bOOM\b/i.test(msg)) {
    return { label: 'OOM 内存', color: 'red' };
  }
  if (/\bconnect(ed|ion)?\b|\baccept(ed)?\b/i.test(msg)) {
    return { label: '连接', color: 'geekblue' };
  }
  return { label: '通知', color: 'default' };
};

// 从 log.file.path 提取部署类型
const extractDeployType = (path: string): string => {
  if (!path) return '--';
  const match = path.match(/redis\/([^/]+)\//);
  return match ? match[1] : '--';
};

const COLUMNS = [
  {
    key: '_time',
    title: '时间',
    dataIndex: '_time',
    width: 130,
    render: formatTime
  },
  {
    key: 'event_type',
    title: '事件类型',
    dataIndex: '_msg',
    width: 120,
    render: (msg: string) => {
      const { label } = detectEventType(msg);
      return (
        <span className="text-xs text-[var(--color-text-1)]">{label}</span>
      );
    }
  },
  {
    key: 'node_ip',
    title: '节点 IP',
    dataIndex: 'node_ip',
    width: 120,
    render: (val: string) =>
      val ? (
        <span className="text-xs font-mono text-[var(--color-text-1)]">
          {val}
        </span>
      ) : (
        <span className="text-[var(--color-text-4)]">--</span>
      )
  },
  {
    key: 'deploy_type',
    title: '部署类型',
    dataIndex: 'log.file.path',
    width: 110,
    render: (val: string) => {
      const t = extractDeployType(val);
      return t !== '--' ? (
        <span className="text-xs text-[var(--color-text-1)]">{t}</span>
      ) : (
        <span className="text-[var(--color-text-4)]">--</span>
      );
    }
  },
  {
    key: '_msg',
    title: '日志内容',
    dataIndex: '_msg',
    render: (val: string) => {
      if (!val) return '--';
      const preview = val.length > 80 ? `${val.slice(0, 80)}…` : val;
      return (
        <Tooltip
          title={
            <pre className="whitespace-pre-wrap text-xs max-w-[520px] max-h-[300px] overflow-auto">
              {val}
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

const RedisLogTable: React.FC<RedisLogTableProps> = ({
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
    const update = () => {
      if (containerRef.current) {
        setScrollY(Math.max(20, containerRef.current.clientHeight - 80));
      }
    };
    update();
    const ro = new ResizeObserver(update);
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={containerRef} className="h-full flex">
      <CustomTable
        className="w-full"
        loading={loading}
        columns={COLUMNS}
        dataSource={tableData}
        rowKey="id"
        size="small"
        scroll={{ x: 'max-content', y: scrollY }}
        virtual
      />
    </div>
  );
};

export default RedisLogTable;
