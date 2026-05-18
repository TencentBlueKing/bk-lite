import React, { useMemo } from 'react';
import { Tag } from 'antd';
import ComTable from '../comTable';
import { DOCKER_LEVEL_COLORS, normalizeDockerLevel } from './dockerLogLevel';

interface DockerLogTailProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

/** 列定义（静态，不依赖 hooks，可在模块顶层定义） */
const LOG_COLUMNS = [
  {
    title: '时间',
    dataIndex: 'time',
    key: 'time',
    width: 72,
    render: (text: string) => (
      <span className="font-mono text-xs text-[var(--color-text-3)]">
        {text}
      </span>
    )
  },
  {
    title: '容器',
    dataIndex: 'container',
    key: 'container',
    width: 88,
    ellipsis: true,
    render: (text: string) => (
      <span className="text-xs font-medium">{text}</span>
    )
  },
  {
    title: '日志流',
    dataIndex: 'stream',
    key: 'stream',
    width: 60,
    render: (text: string) => (
      <span className="text-xs text-[var(--color-text-3)]">{text}</span>
    )
  },
  {
    title: '级别',
    dataIndex: 'level',
    key: 'level',
    width: 56,
    render: (text: string) => {
      if (!text)
        return <span className="text-xs text-[var(--color-text-3)]">--</span>;
      const color =
        DOCKER_LEVEL_COLORS[text as keyof typeof DOCKER_LEVEL_COLORS] ||
        '#8c8c8c';
      return (
        <Tag
          className="m-0 border-0 text-[10px] leading-4 px-1"
          style={{ color, background: `${color}18` }}
        >
          {text}
        </Tag>
      );
    }
  },
  {
    title: '日志内容',
    dataIndex: 'message',
    key: 'message',
    ellipsis: true,
    render: (text: string, record: any) => {
      const isError = record.level === 'ERROR' || record.level === 'FATAL';
      return (
        <span
          className="text-xs"
          style={{ color: isError ? '#f5222d' : undefined }}
        >
          {text}
        </span>
      );
    }
  }
];

const DockerLogTail: React.FC<DockerLogTailProps> = ({
  rawData,
  loading = false,
  config
}) => {
  /** 将原始日志数据转换为表格行 */
  const tableData = useMemo(() => {
    if (!rawData || !Array.isArray(rawData) || rawData.length === 0) return [];

    return rawData.slice(0, 50).map((item: any, idx: number) => {
      const t = item._time || '';
      let formatted = '--';
      if (t) {
        const d = new Date(t);
        formatted = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
      }

      const level = normalizeDockerLevel(item._msg || item.message || '');

      return {
        id: idx,
        time: formatted,
        container: item.container_name || '--',
        stream: item.stream || 'stdout',
        level,
        message: item._msg || item.message || '--'
      };
    });
  }, [rawData]);

  /** ComTable 通过 config.columns 接收列定义，rawData 直接传已转换的行 */
  const tableConfig = { ...(config || {}), columns: LOG_COLUMNS };

  return (
    <ComTable rawData={tableData} loading={loading} config={tableConfig} />
  );
};

export default DockerLogTail;
