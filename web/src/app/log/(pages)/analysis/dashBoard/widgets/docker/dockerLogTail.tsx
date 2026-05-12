import React, { useMemo } from 'react';
import { Empty, Tag, Timeline } from 'antd';
import useChartColors from './useChartColors';

interface DockerLogTailProps {
  rawData: any;
  loading?: boolean;
  config?: any;
}

interface LogEntry {
  key: string;
  time: string;
  container: string;
  message: string;
  stream: string;
}

const DockerLogTail: React.FC<DockerLogTailProps> = ({
  rawData,
  loading = false,
}) => {
  const colors = useChartColors();

  const entries: LogEntry[] = useMemo(() => {
    if (!rawData || !Array.isArray(rawData) || rawData.length === 0) return [];

    return rawData.slice(0, 50).map((item: any, idx: number) => {
      const t = item._time || '';
      let formatted = t;
      if (t) {
        const d = new Date(t);
        formatted = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
      }
      return {
        key: `${idx}`,
        time: formatted,
        container: item.container_name || '--',
        message: item._msg || item.message || '--',
        stream: item.stream || 'stdout'
      };
    });
  }, [rawData]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div
          className="w-5 h-5 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: `${colors.primary}33`, borderTopColor: 'transparent' }}
        />
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  const timelineItems = entries.map((entry) => {
    const isStderr = entry.stream === 'stderr';

    return {
      color: isStderr ? colors.danger : colors.primary,
      children: (
        <div
          className="rounded-md px-3 py-2"
          style={{
            background: isStderr ? `${colors.danger}08` : `${colors.primary}08`,
            border: `1px solid ${isStderr ? `${colors.danger}22` : `${colors.primary}22`}`
          }}
        >
          <div className="mb-1 flex items-center gap-2 text-xs">
            <span
              className="shrink-0 font-mono"
              style={{ color: colors.textTertiary }}
            >
              {entry.time}
            </span>
            <Tag
              className="m-0 text-[10px] leading-4 px-1"
              style={{
                borderColor: isStderr ? colors.danger : colors.primary,
                color: isStderr ? colors.danger : colors.primary,
                background: isStderr ? `${colors.danger}10` : `${colors.primary}10`
              }}
            >
              {entry.container.length > 16
                ? entry.container.slice(0, 16) + '…'
                : entry.container}
            </Tag>
          </div>
          <div
            className="break-all text-xs leading-5"
            style={{ color: isStderr ? colors.danger : colors.textSecondary }}
          >
            {entry.message}
          </div>
        </div>
      )
    };
  });

  return (
    <div className="h-full overflow-auto px-3 py-2">
      <Timeline
        items={timelineItems}
        className="[&_.ant-timeline-item-content]:min-h-0 [&_.ant-timeline-item-content]:pb-3 [&_.ant-timeline-item-last_.ant-timeline-item-content]:pb-0"
      />
    </div>
  );
};

export default DockerLogTail;
