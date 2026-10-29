'use client';

import React, { useMemo } from 'react';
import { Modal, Table, Tag } from 'antd';
import dayjs from 'dayjs';
import {
  AggregateConditionTable,
  formatAggregateReason,
} from '@/app/log/components/aggregateConditionHit';
import { parseRawLogData } from '@/app/log/components/public/alertRawLogEvidence';
import { LEVEL_MAP } from '@/app/log/constants';
import { formatCompareTarget } from '@/app/log/utils/compareTarget';

export interface LogDryRunCondition {
  func?: string;
  field?: string;
  current?: number | null;
  baseline?: number | null;
  value?: number | null;
  op?: string;
  threshold?: string | number;
  matched?: boolean;
  reason?: string;
  compare?: { kind?: string; to?: string };
  level?: string | null;
  thresholds?: Array<{ level: string; value: string | number; matched?: boolean }>;
}

export interface LogDryRunItem {
  group?: Record<string, string>;
  count?: number | null;
  previous_count?: number | null;
  count_rate?: number | null;
  count_delta?: number | null;
  conditions?: LogDryRunCondition[];
  verdict?: string;
  reason?: string;
  no_data?: boolean;
  streak?: number | null;
  level?: string | null;
}

export interface LogDryRunWindow {
  start?: number;
  end?: number;
}

export interface LogDryRunBaseline {
  window?: LogDryRunWindow;
  status?: string;
}

export interface LogDryRunResult {
  alert_type?: string;
  window?: LogDryRunWindow;
  previous_window?: LogDryRunWindow;
  baseline_status?: string;
  baselines?: Record<string, LogDryRunBaseline>;
  items?: LogDryRunItem[];
  truncated?: boolean;
  sample_preview?: Array<Record<string, unknown>>;
}

interface DryRunResultModalProps {
  open: boolean;
  data: LogDryRunResult | null;
  onClose: () => void;
  t: (key: string) => string;
}

const VERDICT_LABEL: Record<string, string> = {
  would_trigger: 'log.event.verdictWouldTrigger',
  no_trigger: 'log.event.verdictNoTrigger',
  missing_baseline: 'log.event.verdictMissingBaseline',
  no_data: 'log.event.verdictNoData',
  would_trigger_no_data: 'log.event.verdictWouldTriggerNoData',
};

const formatWindow = (window?: LogDryRunWindow) => {
  if (!window || window.start == null || window.end == null) {
    return '—';
  }
  const start = dayjs.unix(window.start).format('YYYY-MM-DD HH:mm:ss');
  const end = dayjs.unix(window.end).format('YYYY-MM-DD HH:mm:ss');
  return `${start} ~ ${end}`;
};

const formatGroup = (group: Record<string, string> | undefined, allLabel: string) => {
  const entries = Object.entries(group || {}).filter(([, value]) => value !== undefined && value !== '');
  if (!entries.length) {
    return allLabel;
  }
  return entries.map(([key, value]) => `${key}=${value}`).join(', ');
};

const formatCount = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }
  return String(value);
};

const formatRate = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }
  return Number(value).toFixed(2);
};

const VerdictTag = ({
  verdict,
  level,
  t,
}: {
  verdict?: string;
  level?: string | null;
  t: (key: string) => string;
}) => {
  const label = t(VERDICT_LABEL[verdict || ''] || verdict || '—');
  if (verdict === 'would_trigger') {
    const levelColor = level ? LEVEL_MAP[level] : '';
    const text = level ? `${label} ${t(`log.event.${level}`)}` : label;
    return (
      <Tag
        data-testid="dry-run-verdict-would-trigger"
        style={
          levelColor
            ? { color: levelColor, borderColor: levelColor }
            : { color: 'var(--color-fail)', borderColor: 'var(--color-fail)' }
        }
      >
        {text}
      </Tag>
    );
  }
  if (verdict === 'missing_baseline' || verdict === 'would_trigger_no_data') {
    return <Tag color="warning">{label}</Tag>;
  }
  return <Tag>{label}</Tag>;
};

const DryRunResultModal: React.FC<DryRunResultModalProps> = ({ open, data, onClose, t }) => {
  const items = data?.items || [];
  const baselines = Object.entries(data?.baselines || {});
  const keyword = data?.alert_type === 'keyword';
  const showPreviousWindow = Boolean(data?.baseline_status && data.baseline_status !== 'not_required');
  const verdictCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    items.forEach((item) => {
      const verdict = item.verdict || '';
      if (!verdict) {
        return;
      }
      counts[verdict] = (counts[verdict] || 0) + 1;
    });
    return counts;
  }, [items]);

  const tableItems = useMemo(
    () => items.map((item, index) => ({ ...item, rowKey: String(index) })),
    [items],
  );
  const showStreak = items.some((item) => typeof item.streak === 'number');

  const columns = useMemo(() => {
    const groupColumn = {
      title: t('log.event.dryRunGroup'),
      dataIndex: 'group',
      key: 'group',
      render: (group: Record<string, string> | undefined) => formatGroup(group, t('common.all')),
    };
    const countColumn = {
      title: t('log.event.currentCount'),
      dataIndex: 'count',
      key: 'count',
      render: (value: number | null | undefined, record: LogDryRunItem) =>
        record.no_data || record.verdict === 'would_trigger_no_data'
          ? t('log.event.currentWindowEmpty')
          : formatCount(value),
    };
    const streakColumn = {
      title: t('log.event.streak'),
      dataIndex: 'streak',
      key: 'streak',
      render: (value: number | null | undefined) => formatCount(value),
    };
    const verdictColumn = {
      title: t('log.event.dryRunVerdict'),
      dataIndex: 'verdict',
      key: 'verdict',
      render: (verdict: string, record: LogDryRunItem) => (
        <span className="inline-flex flex-wrap items-center gap-1">
          <VerdictTag verdict={verdict} level={record.level} t={t} />
          {record.reason === 'window_failed' ? <span>{formatAggregateReason(record.reason, t)}</span> : null}
        </span>
      ),
    };
    const leading = showStreak
      ? [groupColumn, countColumn, streakColumn]
      : [groupColumn, countColumn];
    if (keyword) {
      return [...leading, verdictColumn];
    }
    return [
      ...leading,
      {
        title: t('log.event.previousCount'),
        dataIndex: 'previous_count',
        key: 'previous_count',
        render: (value: number | null | undefined) => formatCount(value),
      },
      {
        title: t('log.event.countRate'),
        dataIndex: 'count_rate',
        key: 'count_rate',
        render: (value: number | null | undefined) => formatRate(value),
      },
      {
        title: t('log.event.countDelta'),
        dataIndex: 'count_delta',
        key: 'count_delta',
        render: (value: number | null | undefined) => formatCount(value),
      },
      verdictColumn,
    ];
  }, [keyword, showStreak, t]);

  const sample = useMemo(() => parseRawLogData(data?.sample_preview || []), [data?.sample_preview]);

  return (
    <Modal
      open={open}
      title={t('log.event.dryRunResult')}
      onCancel={onClose}
      footer={null}
      width={960}
      destroyOnHidden
    >
      <div className="mb-3 flex flex-wrap gap-4 text-[13px] text-[var(--color-text-2)]">
        <span>
          <span>{t('log.event.dryRunWindow')}</span>
          {': '}
          {formatWindow(data?.window)}
        </span>
        {showPreviousWindow ? (
          <span data-testid="dry-run-previous-window">
            <span>{t('log.event.dryRunPreviousWindow')}</span>
            {': '}
            {formatWindow(data?.previous_window)}
          </span>
        ) : null}
        {baselines.map(([target, info]) => (
          <span key={target} data-testid={`dry-run-baseline-${target}`}>
            <span>{formatCompareTarget(target, undefined, t)}</span>
            {': '}
            {formatWindow(info.window)}
            {' '}
            {info.status}
          </span>
        ))}
      </div>
      {items.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-2">
          {Object.entries(verdictCounts).map(([verdict, count]) => (
            <span
              key={verdict}
              className="rounded-full border border-[var(--color-border)] px-2 py-[2px] text-[12px] text-[var(--color-text-2)]"
            >
              {t(VERDICT_LABEL[verdict] || verdict)} {count}
            </span>
          ))}
        </div>
      ) : (
        <div className="mb-3 text-[13px] text-[var(--color-text-3)]">{t('log.event.dryRunNoMatch')}</div>
      )}
      {data?.truncated ? (
        <div className="mb-3 text-[13px] text-[var(--color-warning)]">{t('log.event.truncatedHint')}</div>
      ) : null}
      {items.length > 0 ? (
        <Table
          size="small"
          pagination={false}
          rowKey="rowKey"
          dataSource={tableItems}
          columns={columns}
          expandable={{
            rowExpandable: (record) => Array.isArray(record.conditions) && record.conditions.length > 0,
            expandedRowRender: (record) => (
              <AggregateConditionTable conditions={record.conditions || []} t={t} />
            ),
          }}
        />
      ) : null}
      {sample.isTabular && sample.rows.length > 0 ? (
        <Table
          className="mt-4"
          size="small"
          pagination={false}
          rowKey="__id"
          dataSource={sample.rows}
          columns={sample.columns.map((column) => ({
            title: column.title,
            dataIndex: column.dataIndex,
            key: column.key,
            width: column.width,
          }))}
        />
      ) : null}
    </Modal>
  );
};

export default DryRunResultModal;
