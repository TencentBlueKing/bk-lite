import React from 'react';
import { Button, InputNumber, Select, Tooltip } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { LEVEL_MAP } from '@/app/monitor/constants';
import { COMPARISON_METHOD } from '@/app/monitor/constants/event';
import { UnitListItem } from '@/app/monitor/types';
import { MetricExpressionRow } from './metricExpressionTypes';
import {
  addMultiLevel,
  multiLevelRows,
  removeMultiLevel,
  setMultiLevelCell
} from './formulaExpressionUtils';
import {
  getThresholdValuePlaceholder,
  resolveMetricDisplayUnit
} from './strategyDetailUtils';
import { STRATEGY_HINT_TEXT_CLASS } from './alertDurationFields';

const CANONICAL_LEVELS = ['critical', 'error', 'warning'];

const COMPARISON_OPTIONS = COMPARISON_METHOD.flatMap((item) => {
  if (item.value == null) {
    return [];
  }
  return [{
    label: String(item.label ?? item.value),
    value: String(item.value)
  }];
});

interface MultiThresholdGridProps {
  rows: MetricExpressionRow[];
  unitList: UnitListItem[];
  onChange: (rows: MetricExpressionRow[]) => void;
}

const conditionName = (row: MetricExpressionRow): string => {
  if (row.source === 'formula') {
    return String(row.resultName || '');
  }
  return row.metricLabel || row.metricName || row.ref;
};

const legendLabel = (row: MetricExpressionRow): string => {
  const name = conditionName(row);
  if (!name || name === row.ref) {
    return row.ref;
  }
  return `${row.ref} ${name}`;
};

const MultiThresholdGrid: React.FC<MultiThresholdGridProps> = ({
  rows,
  unitList,
  onChange
}) => {
  const { t } = useTranslation();
  const levelConditions = rows.filter((row) => (row.role || 'level') === 'level');
  const gateConditions = rows.filter((row) => row.role === 'gate');
  const levels = multiLevelRows(rows);
  const canAdd =
    levelConditions.length > 0 &&
    CANONICAL_LEVELS.some((level) => !levels.includes(level));

  const thresholdCell = (
    row: MetricExpressionRow,
    field: { method?: string; value?: number | null } | undefined,
    onMethod: (method: string) => void,
    onValue: (value: number | null) => void
  ) => {
    const unit = resolveMetricDisplayUnit(row.thresholdUnit, unitList);
    return (
      <div className="flex min-w-[220px] items-center gap-2">
        <Tooltip title={conditionName(row) || row.ref}>
          <span className="shrink-0 text-[var(--color-text-2)]">{row.ref}</span>
        </Tooltip>
        <div className="w-[88px] shrink-0">
          <Select
            className="w-[88px]"
            value={field?.method || undefined}
            placeholder={t('monitor.events.method')}
            options={COMPARISON_OPTIONS}
            onChange={onMethod}
          />
        </div>
        <div className="w-[112px] shrink-0">
          <InputNumber
            className="w-full"
            addonAfter={unit || undefined}
            value={field?.value ?? null}
            placeholder={getThresholdValuePlaceholder(row.thresholdUnit)}
            onChange={(next) => onValue(typeof next === 'number' ? next : null)}
          />
        </div>
      </div>
    );
  };

  return (
    <div className="w-full rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-4 shadow-md">
      {levelConditions.length > 0 ? (
        <div className={`mb-3 pl-[84px] ${STRATEGY_HINT_TEXT_CLASS}`}>
          {levelConditions.map(legendLabel).join(' · ')}
        </div>
      ) : null}
      <div className="flex flex-col gap-2">
        {levels.map((level) => (
          <div
            key={level}
            className="flex flex-wrap items-center gap-x-3 gap-y-2"
          >
            <span className="inline-flex w-[72px] shrink-0 items-center gap-2 text-sm text-[var(--color-text-1)]">
              <span
                className="inline-block h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: String(LEVEL_MAP[level] || 'var(--color-text-3)') }}
              />
              {t(`monitor.events.${level}`)}
            </span>
            {levelConditions.map((row, index) => {
              const field = (row.threshold || []).find((item) => item.level === level);
              return (
                <div key={row.ref} className="contents">
                  {index > 0 ? (
                    <span className="shrink-0 text-sm text-[var(--color-text-3)]">
                      {t('common.and')}
                    </span>
                  ) : null}
                  {thresholdCell(
                    row,
                    field,
                    (method) => onChange(setMultiLevelCell(rows, row.ref, level, { method })),
                    (value) => onChange(setMultiLevelCell(rows, row.ref, level, { value }))
                  )}
                </div>
              );
            })}
            <Button
              type="link"
              size="small"
              className="ml-auto shrink-0 px-0"
              aria-label={t('monitor.events.multiRemoveLevel')}
              icon={<MinusCircleOutlined />}
              onClick={() => onChange(removeMultiLevel(rows, level))}
            />
          </div>
        ))}
        {canAdd ? (
          <div>
            <Button
              type="link"
              size="small"
              className="px-0"
              icon={<PlusOutlined />}
              onClick={() => onChange(addMultiLevel(rows))}
            >
              {t('monitor.events.multiAddLevel')}
            </Button>
          </div>
        ) : null}
      </div>
      {gateConditions.length > 0 ? (
        <div className="mt-3 border-t border-[var(--color-border-2)] pt-3">
          <div className="mb-2 text-sm text-[var(--color-text-1)]">
            {t('monitor.events.multiRoleGate')}
          </div>
          <div className="flex flex-col gap-2">
            {gateConditions.map((row) => (
              <div
                key={row.ref}
                className="flex flex-wrap items-center gap-x-3 gap-y-2"
              >
                <span className="w-[72px] shrink-0" />
                {thresholdCell(
                  row,
                  row.threshold?.[0],
                  (method) =>
                    onChange(
                      rows.map((item) =>
                        item.ref === row.ref
                          ? {
                            ...item,
                            threshold: [{
                              method,
                              value: item.threshold?.[0]?.value ?? null
                            }]
                          }
                          : item
                      )
                    ),
                  (value) =>
                    onChange(
                      rows.map((item) =>
                        item.ref === row.ref
                          ? {
                            ...item,
                            threshold: [{
                              method: item.threshold?.[0]?.method || '>',
                              value
                            }]
                          }
                          : item
                      )
                    )
                )}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default MultiThresholdGrid;
