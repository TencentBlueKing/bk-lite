'use client';

import React, { useMemo } from 'react';
import { Modal, Table, Tag } from 'antd';
import dayjs from 'dayjs';
import {
  AggregateHitCondition,
  aggregateConditionText,
  formatAggregateMetric,
  formatAggregateReason,
  thresholdLadderPieces,
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
  role?: string;
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

const asHitCondition = (condition: LogDryRunCondition): AggregateHitCondition => condition;

/** 绝对比较只留算出的那个数。变化量、变化率才把当前值和对照值写出来。 */
function conditionFigure(condition: LogDryRunCondition, t: (key: string) => string) {
  const relative = Boolean(condition.compare?.kind && condition.compare.kind !== 'absolute');
  const valueText = formatAggregateMetric(condition.value);
  if (!relative && condition.baseline == null) {
    return <span>{valueText}</span>;
  }
  const currentText = formatAggregateMetric(condition.current);
  const baselineText = formatAggregateMetric(condition.baseline);
  return (
    <span className="inline-flex flex-wrap gap-x-3 gap-y-1">
      {relative || currentText !== valueText ? (
        <span className="inline-flex items-baseline gap-1">
          <span className="text-[var(--color-text-3)]">{t('log.event.currentValue')}</span>
          <span>{currentText}</span>
        </span>
      ) : null}
      {relative || condition.baseline != null ? (
        <span className="inline-flex items-baseline gap-1">
          <span className="text-[var(--color-text-3)]">{t('log.event.baselineValue')}</span>
          <span>{baselineText}</span>
        </span>
      ) : null}
      <span className="inline-flex items-baseline gap-1">
        <span className="text-[var(--color-text-3)]">{t('log.event.computedValue')}</span>
        <span>{valueText}</span>
      </span>
    </span>
  );
}

function conditionMark(condition: LogDryRunCondition, t: (key: string) => string) {
  if (condition.role === 'guard') {
    return condition.matched ? t('log.event.guardPassed') : t('log.event.guardMissed');
  }
  if (condition.matched && condition.level) {
    return t(`log.event.${condition.level}`);
  }
  return '';
}

function DryRunChecks({
  conditions,
  t,
}: {
  conditions: LogDryRunCondition[];
  t: (key: string) => string;
}) {
  return (
    <div className="flex flex-col">
      {conditions.map((condition, index) => {
        const hit = asHitCondition(condition);
        const pieces = thresholdLadderPieces(hit);
        const reason = condition.reason ? formatAggregateReason(condition.reason, t) : '';
        const mark = conditionMark(condition, t);
        const levelColor = condition.matched && condition.level ? LEVEL_MAP[condition.level] : '';
        return (
          <div
            key={`${condition.func || 'condition'}-${index}`}
            className="flex items-baseline gap-x-6 border-t border-[var(--color-border-1)] py-2.5 text-[13px]"
          >
            <div className="w-36 shrink-0 text-[var(--color-text-1)]">{aggregateConditionText(hit, t)}</div>
            <div className="w-12 shrink-0 tabular-nums text-[var(--color-text-1)]">{conditionFigure(condition, t)}</div>
            <div className="min-w-0">
              {pieces ? (
                <span className="inline-flex flex-wrap gap-x-3 gap-y-1">
                  {pieces.map((piece) => (
                    <span
                      key={piece.level}
                      className={piece.hit ? 'font-semibold' : 'text-[var(--color-text-2)]'}
                      style={piece.hit && LEVEL_MAP[piece.level] ? { color: LEVEL_MAP[piece.level] } : undefined}
                    >
                      {`${piece.text}（${t(`log.event.${piece.level}`)}）`}
                    </span>
                  ))}
                </span>
              ) : (
                <span className="text-[var(--color-text-2)]">
                  {`${condition.op || ''} ${condition.threshold ?? ''}`.trim() || '—'}
                </span>
              )}
              {reason && reason !== '—' ? (
                <div className="mt-0.5 text-[12px] text-[var(--color-text-3)]">{reason}</div>
              ) : null}
            </div>
            {mark ? (
              <div className="shrink-0" style={levelColor ? { color: levelColor } : undefined}>
                {mark}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/** 一条分组就是一条告警实例。没有分组时也是这一块，名字用「全部」。 */
function DryRunInstance({
  item,
  keyword,
  t,
}: {
  item: LogDryRunItem;
  keyword: boolean;
  t: (key: string) => string;
}) {
  const conditions = keyword ? [] : item.conditions || [];
  return (
    <section className="border-b border-[var(--color-border-1)] py-3 last:border-b-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="min-w-0 break-all text-[13px] font-medium text-[var(--color-text-1)]">
          {formatGroup(item.group, t('common.all'))}
        </span>
        <span className="inline-flex flex-wrap items-baseline gap-x-3 text-[13px] text-[var(--color-text-2)]">
          {item.no_data || item.verdict === 'would_trigger_no_data' ? (
            <span>{t('log.event.currentWindowEmpty')}</span>
          ) : (
            <span className="inline-flex items-baseline gap-1">
              <span>{t('log.event.currentCount')}</span>
              <span>{formatCount(item.count)}</span>
            </span>
          )}
          {typeof item.streak === 'number' ? (
            <span className="inline-flex items-baseline gap-1">
              <span>{t('log.event.streak')}</span>
              <span>{formatCount(item.streak)}</span>
            </span>
          ) : null}
          {item.previous_count != null ? (
            <span className="inline-flex items-baseline gap-1">
              <span>{t('log.event.previousCount')}</span>
              <span>{formatCount(item.previous_count)}</span>
            </span>
          ) : null}
          {item.count_rate != null ? (
            <span className="inline-flex items-baseline gap-1">
              <span>{t('log.event.countRate')}</span>
              <span>{formatRate(item.count_rate)}</span>
            </span>
          ) : null}
          {item.count_delta != null ? (
            <span className="inline-flex items-baseline gap-1">
              <span>{t('log.event.countDelta')}</span>
              <span>{formatCount(item.count_delta)}</span>
            </span>
          ) : null}
        </span>
        <span className="ml-auto inline-flex items-center gap-2">
          {item.reason === 'window_failed' ? (
            <span className="text-[13px] text-[var(--color-text-2)]">{formatAggregateReason(item.reason, t)}</span>
          ) : null}
          <VerdictTag verdict={item.verdict} level={item.level} t={t} />
        </span>
      </div>
      {conditions.length > 0 ? <DryRunChecks conditions={conditions} t={t} /> : null}
    </section>
  );
}

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

  const sample = useMemo(() => parseRawLogData(data?.sample_preview || []), [data?.sample_preview]);

  return (
    <Modal
      open={open}
      title={t('log.event.dryRunResult')}
      onCancel={onClose}
      footer={null}
      width={960}
      destroyOnHidden
      styles={{ body: { maxHeight: '70vh', overflowY: 'auto' } }}
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
      {items.length > 1 ? (
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
      ) : null}
      {items.length === 0 ? (
        <div className="mb-3 text-[13px] text-[var(--color-text-3)]">{t('log.event.dryRunNoMatch')}</div>
      ) : null}
      {data?.truncated ? (
        <div className="mb-3 text-[13px] text-[var(--color-warning)]">{t('log.event.truncatedHint')}</div>
      ) : null}
      {items.length > 0 ? (
        <div>
          {items.map((item, index) => (
            <DryRunInstance key={index} item={item} keyword={keyword} t={t} />
          ))}
        </div>
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
