import React, { useEffect, useMemo } from 'react';
import { Empty, Spin } from 'antd';
import dayjs from 'dayjs';
import { formatOpsDisplayTime } from '@/app/ops-analysis/utils/dateTime';
import { useTranslation } from '@/utils/i18n';

interface ComMessageProps {
  rawData: unknown;
  loading?: boolean;
  onReady?: (ready: boolean) => void;
}

interface MessageRow {
  __id: string;
  timestamp: string;
  level: string;
  source: string;
  message: string;
  rawTime: string;
}

const LEVEL_COLOR_MAP: Record<string, string> = {
  critical: '#F43B2C',
  fatal: '#F43B2C',
  error: '#D97007',
  err: '#D97007',
  warning: '#FFAD42',
  warn: '#FFAD42',
  info: '#3A84FF',
  notice: '#3A84FF',
  debug: '#8E9AA8',
  trace: '#8E9AA8',
};

const pickField = (item: Record<string, unknown>, candidates: string[]) => {
  for (const key of candidates) {
    if (
      item[key] !== undefined &&
      item[key] !== null &&
      String(item[key]).trim() !== ''
    ) {
      return String(item[key]);
    }
  }
  return '';
};

const normalizeRows = (rawData: unknown): MessageRow[] => {
  const list = Array.isArray(rawData)
    ? rawData
    : rawData &&
        typeof rawData === 'object' &&
        Array.isArray((rawData as Record<string, unknown>).items)
      ? ((rawData as Record<string, unknown>).items as unknown[])
      : [];

  return list
    .map((item, index) => {
      if (!item || typeof item !== 'object') {
        return null;
      }

      const objectItem = item as Record<string, unknown>;
      const rawTime = pickField(objectItem, [
        'timestamp',
        'time',
        '_time',
        'event_time',
        'created_at',
        'ts',
      ]);
      const level = pickField(objectItem, [
        'level',
        'severity',
        'log_level',
        'event_level',
        'status',
      ]);
      const source = pickField(objectItem, [
        'source',
        'service',
        'module',
        'component',
        'host',
        'event_source',
      ]);
      const message = pickField(objectItem, [
        'message',
        'msg',
        'content',
        'detail',
        'body',
        'text',
      ]);

      if (!rawTime || !message) {
        return null;
      }

      const formattedTime = dayjs(rawTime).isValid()
        ? formatOpsDisplayTime(rawTime, 'MM-DD HH:mm:ss')
        : rawTime;

      return {
        __id: `${index}_${rawTime}_${message.slice(0, 12)}`,
        timestamp: formattedTime,
        level: level || '-',
        source: source || '-',
        message,
        rawTime,
      };
    })
    .filter((row): row is MessageRow => Boolean(row))
    .sort((a, b) => dayjs(b.rawTime).valueOf() - dayjs(a.rawTime).valueOf());
};

const getLevelColor = (level: string) => {
  const normalized = (level || '').toLowerCase();
  return LEVEL_COLOR_MAP[normalized] || '#63656E';
};

const ComMessage: React.FC<ComMessageProps> = ({
  rawData,
  loading = false,
  onReady,
}) => {
  const { t } = useTranslation();
  const rows = useMemo(() => normalizeRows(rawData), [rawData]);

  useEffect(() => {
    if (!loading) {
      onReady?.(rows.length > 0);
    }
  }, [loading, onReady, rows.length]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Spin size="small" />
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div className="h-full flex items-center justify-center">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="grid grid-cols-[136px_110px_120px_minmax(0,1fr)] px-3 py-2 text-xs font-medium text-(--color-text-3) border-b border-(--color-border-1)">
        <span>{t('dashboard.messageTime')}</span>
        <span>{t('dashboard.messageLevel')}</span>
        <span>{t('dashboard.messageSource')}</span>
        <span>{t('dashboard.messageContent')}</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {rows.map((row) => (
          <div
            key={row.__id}
            className="grid grid-cols-[136px_110px_120px_minmax(0,1fr)] gap-x-2 px-3 py-2 border-b border-(--color-border-1) text-xs text-(--color-text-2)"
          >
            <span className="truncate" title={row.timestamp}>
              {row.timestamp}
            </span>
            <span
              className="inline-flex w-fit items-center rounded-full px-2 py-0.5 text-[11px] font-semibold"
              style={{
                color: getLevelColor(row.level),
                backgroundColor: `${getLevelColor(row.level)}1A`,
              }}
            >
              {row.level}
            </span>
            <span className="truncate" title={row.source}>
              {row.source}
            </span>
            <span className="truncate" title={row.message}>
              {row.message}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ComMessage;
