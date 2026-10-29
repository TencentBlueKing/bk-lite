'use client';

import { COMPARE_KIND_LIST, FUNCTION_LIST, LEVEL_MAP } from '@/app/log/constants';
import { formatCompareTarget } from '@/app/log/utils/compareTarget';
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
  if (typeof value === 'number' && !Number.isInteger(value)) {
    return value.toFixed(2);
  }
  return String(value);
};

export const thresholdLadderPieces = (condition: AggregateHitCondition) => {
  if (condition.role === 'guard' || !condition.thresholds?.length) {
    return null;
  }
  return condition.thresholds.map((step) => ({
    level: step.level,
    text: `${condition.op || ''} ${step.value ?? ''}`.trim(),
    hit: Boolean(step.matched),
  }));
};

export const formatAggregateReason = (reason: string | undefined, t: Translate) => {
  if (!reason) {
    return '—';
  }
  return t(REASON_LABEL[reason] || reason);
};

const labelOf = (list: Array<{ value: string; labelKey: string }>, value: string | undefined, t: Translate) => {
  const item = list.find((entry) => entry.value === value);
  return item ? t(item.labelKey) : value || '';
};

/** 条件列：函数中文名、字段或分子筛选、比较方式与对照。与表单用同一套词条。 */
export const aggregateConditionText = (condition: AggregateHitCondition, t: Translate) => {
  const func = condition.func || '';
  const funcName = labelOf(FUNCTION_LIST, func, t) || func;
  let name = funcName;
  if (func === 'quantile') {
    const quantile = condition.params?.quantile;
    const mark = typeof quantile === 'number' ? `P${Math.round(quantile * 100)}` : funcName;
    name = condition.field && condition.field !== '_msg' ? `${mark}(${condition.field})` : mark;
  } else if (func === 'ratio') {
    const filter = condition.params?.filter;
    name = filter ? `${funcName}(${filter})` : funcName;
  } else if (condition.field && condition.field !== '_msg') {
    name = `${funcName}(${condition.field})`;
  }
  const kind = condition.compare?.kind;
  const prefix = condition.role === 'guard' ? `${t('log.event.roleGuard')} ` : '';
  if (kind && kind !== 'absolute') {
    const kindText = labelOf(COMPARE_KIND_LIST, kind, t);
    const targetText = formatCompareTarget(condition.compare?.to, condition.compare?.offset, t);
    name = targetText ? `${name}（${kindText} / ${targetText}）` : `${name}（${kindText}）`;
  }
  return `${prefix}${name}`;
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

/** 详情「原始日志」优先样本；没有样本时退回聚合结果行。 */
export function aggregateDetailRows(data: unknown): unknown[] {
  if (Array.isArray(data)) {
    return data;
  }
  if (!data || typeof data !== 'object') {
    return [];
  }
  const record = data as { samples?: unknown; query_result?: unknown };
  if (Array.isArray(record.samples) && record.samples.length > 0) {
    return record.samples;
  }
  if (record.query_result && typeof record.query_result === 'object') {
    return [record.query_result];
  }
  return [];
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

const hasNumber = (value: number | null | undefined) =>
  value !== null && value !== undefined && !Number.isNaN(Number(value));

/** 绝对比较的当前值和算出值是同一个数，对照又是空的。只在变化量、变化率上把三列都写出来。 */
function conditionMetrics(condition: AggregateHitCondition) {
  const relative = Boolean(condition.compare?.kind && condition.compare.kind !== 'absolute');
  const currentText = formatAggregateMetric(condition.current);
  const valueText = formatAggregateMetric(condition.value);
  return {
    showCurrent: relative || (hasNumber(condition.current) && currentText !== valueText),
    showBaseline: relative || hasNumber(condition.baseline),
    currentText,
    baselineText: formatAggregateMetric(condition.baseline),
    valueText,
  };
}

function conditionOutcome(condition: AggregateHitCondition, t: Translate) {
  if (condition.role === 'guard') {
    return condition.matched ? t('log.event.guardPassed') : t('log.event.guardMissed');
  }
  return condition.matched ? t('log.event.verdictWouldTrigger') : t('log.event.verdictNoTrigger');
}

export function AggregateConditionTable({
  conditions,
  t,
}: {
  conditions: AggregateHitCondition[];
  t: Translate;
}) {
  return (
    <div data-testid="aggregate-condition-table" className="flex flex-col">
      {conditions.map((condition, index) => {
        const metrics = conditionMetrics(condition);
        const pieces = thresholdLadderPieces(condition);
        const reason = condition.reason ? formatAggregateReason(condition.reason, t) : '';
        const levelColor = condition.level ? LEVEL_MAP[condition.level] : '';
        return (
          <div
            key={`${condition.func || 'condition'}-${index}`}
            className="grid grid-cols-[minmax(7.5rem,1.15fr)_minmax(0,1.35fr)_minmax(0,1.7fr)_auto] items-baseline gap-x-4 border-b border-[var(--color-border-1)] py-2 text-[13px] last:border-b-0"
          >
            <div className="min-w-0 text-[var(--color-text-1)]">{aggregateConditionText(condition, t)}</div>
            <div className="flex min-w-0 flex-wrap gap-x-3 gap-y-1 text-[var(--color-text-1)]">
              {metrics.showCurrent ? (
                <span className="inline-flex items-baseline gap-1">
                  <span className="text-[var(--color-text-3)]">{t('log.event.currentValue')}</span>
                  <span>{metrics.currentText}</span>
                </span>
              ) : null}
              {metrics.showBaseline ? (
                <span className="inline-flex items-baseline gap-1">
                  <span className="text-[var(--color-text-3)]">{t('log.event.baselineValue')}</span>
                  <span>{metrics.baselineText}</span>
                </span>
              ) : null}
              <span className="inline-flex items-baseline gap-1">
                <span className="text-[var(--color-text-3)]">{t('log.event.computedValue')}</span>
                <span>{metrics.valueText}</span>
              </span>
            </div>
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
            </div>
            <div className="text-right">
              <div style={condition.matched && levelColor ? { color: levelColor } : undefined}>
                {conditionOutcome(condition, t)}
              </div>
              {reason && reason !== '—' ? (
                <div className="mt-0.5 text-[12px] text-[var(--color-text-3)]">{reason}</div>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
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
