'use client';

import React, { useMemo } from 'react';
import { Table } from 'antd';
import {
  AggregateResultCondition,
  AggregateResultHit,
} from '@/app/log/components/public/alertRawLogEvidence';

export type AggregateHitCondition = AggregateResultCondition;

type Translate = (
  key: string,
  defaultMessage?: string,
  values?: { count?: number | string },
) => string;

const REASON_LABEL: Record<string, string> = {
  missing_baseline: 'log.event.verdictMissingBaseline',
  baseline_zero: 'log.event.reasonBaselineZero',
  baseline_missing: 'log.event.reasonBaselineMissing',
  not_numeric: 'log.event.reasonNotNumeric',
  denominator_zero: 'log.event.reasonDenominatorZero',
  window_failed: 'log.event.reasonWindowFailed',
};

export const formatAggregateMetric = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }
  return String(value);
};

export const formatAggregateReason = (reason: string | undefined, t: Translate) => {
  if (!reason) {
    return '—';
  }
  return t(REASON_LABEL[reason] || reason);
};

export const aggregateConditionText = (condition: AggregateHitCondition) => {
  const func = condition.func || '';
  const field = condition.field && condition.field !== '_msg' ? `(${condition.field})` : '';
  const kind = condition.compare?.kind && condition.compare.kind !== 'absolute' ? ` ${condition.compare.kind}` : '';
  return `${func}${field}${kind}`;
};

export function readRawAggregateResult(rawData: unknown): AggregateResultHit | null {
  if (!rawData || typeof rawData !== 'object' || Array.isArray(rawData)) {
    return null;
  }
  const aggregate = (rawData as { aggregate_result?: unknown }).aggregate_result;
  if (!aggregate || typeof aggregate !== 'object' || Array.isArray(aggregate)) {
    return null;
  }
  return aggregate as AggregateResultHit;
}

export function readEventAggregateResult(responseData: unknown): AggregateResultHit | null {
  if (!responseData || typeof responseData !== 'object') {
    return null;
  }
  const data = (responseData as { raw_data?: { data?: unknown } }).raw_data?.data;
  return readRawAggregateResult(data);
}

export function readAggregateConditions(aggregateResult: unknown): AggregateHitCondition[] | null {
  if (!aggregateResult || typeof aggregateResult !== 'object' || Array.isArray(aggregateResult)) {
    return null;
  }
  const raw = (aggregateResult as { conditions?: unknown }).conditions;
  if (!Array.isArray(raw) || raw.length === 0) {
    return null;
  }
  const conditions = raw.filter((item) => item && typeof item === 'object') as AggregateHitCondition[];
  return conditions.length > 0 ? conditions : null;
}

export function previousWindowCount(aggregateResult: unknown): number {
  if (!aggregateResult || typeof aggregateResult !== 'object') {
    return 0;
  }
  const baseline = (aggregateResult as { baseline?: { values?: Record<string, unknown> } }).baseline;
  const values = baseline?.values;
  const raw = values?.count__msg ?? values?.count ?? 0;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : 0;
}

export function aggregateNoDataMessage(aggregateResult: unknown, t: Translate): string | null {
  if (!aggregateResult || typeof aggregateResult !== 'object' || Array.isArray(aggregateResult)) {
    return null;
  }
  if ((aggregateResult as { no_data?: unknown }).no_data !== true) {
    return null;
  }
  return t('log.event.noDataWindowLine', undefined, { count: previousWindowCount(aggregateResult) });
}

export function AggregateConditionTable({
  conditions,
  t,
}: {
  conditions: AggregateHitCondition[];
  t: Translate;
}) {
  const columns = useMemo(
    () => [
      {
        title: t('log.event.conditionColumn'),
        key: 'condition',
        render: (_value: unknown, condition: AggregateHitCondition) => aggregateConditionText(condition),
      },
      {
        title: t('log.event.currentValue'),
        dataIndex: 'current',
        key: 'current',
        render: (value: number | null | undefined) => formatAggregateMetric(value),
      },
      {
        title: t('log.event.baselineValue'),
        dataIndex: 'baseline',
        key: 'baseline',
        render: (value: number | null | undefined) => formatAggregateMetric(value),
      },
      {
        title: t('log.event.computedValue'),
        dataIndex: 'value',
        key: 'value',
        render: (value: number | null | undefined) => formatAggregateMetric(value),
      },
      {
        title: t('log.event.threshold'),
        key: 'threshold',
        render: (_value: unknown, condition: AggregateHitCondition) =>
          `${condition.op || ''} ${condition.threshold ?? ''}`.trim(),
      },
      {
        title: t('log.event.matched'),
        dataIndex: 'matched',
        key: 'matched',
        render: (matched: boolean | undefined) =>
          matched ? t('log.event.verdictWouldTrigger') : t('log.event.verdictNoTrigger'),
      },
      {
        title: t('log.event.reason'),
        dataIndex: 'reason',
        key: 'reason',
        render: (reason: string | undefined) => formatAggregateReason(reason, t),
      },
    ],
    [t],
  );

  return (
    <Table
      data-testid="aggregate-condition-table"
      size="small"
      pagination={false}
      rowKey="key"
      dataSource={conditions.map((condition, index) => ({ ...condition, key: String(index) }))}
      columns={columns}
    />
  );
}

export function AggregateHitSummary({
  aggregateResult,
  t,
}: {
  aggregateResult: unknown;
  t: Translate;
}) {
  const noDataText = aggregateNoDataMessage(aggregateResult, t);
  const conditions = readAggregateConditions(aggregateResult);
  if (!noDataText && !conditions) {
    return null;
  }
  return (
    <div className="mb-3 flex flex-col gap-2" data-testid="aggregate-hit">
      {noDataText ? <div data-testid="aggregate-no-data-line">{noDataText}</div> : null}
      {conditions ? <AggregateConditionTable conditions={conditions} t={t} /> : null}
    </div>
  );
}
