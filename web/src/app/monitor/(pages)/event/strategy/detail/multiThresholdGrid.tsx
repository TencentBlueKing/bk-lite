import React from 'react';
import { Button, InputNumber, Select } from 'antd';
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

const ConditionHeading: React.FC<{ row: MetricExpressionRow }> = ({ row }) => {
  const name = conditionName(row);
  const showName = Boolean(name) && name !== row.ref;
  return (
    <div className="flex min-w-0 items-center gap-1.5" title={showName ? name : row.ref}>
      <span className="inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] px-1 font-mono text-xs font-semibold text-[var(--color-primary)]">
        {row.ref}
      </span>
      {showName ? (
        <span className="truncate text-xs text-[var(--color-text-2)]">{name}</span>
      ) : null}
    </div>
  );
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

  const columnStyle = {
    gridTemplateColumns: `72px repeat(${Math.max(levelConditions.length, 1)}, minmax(200px, 1fr)) 32px`
  };

  const thresholdCell = (
    row: MetricExpressionRow,
    field: { method?: string; value?: number | null } | undefined,
    onMethod: (method: string) => void,
    onValue: (value: number | null) => void
  ) => {
    const unit = resolveMetricDisplayUnit(row.thresholdUnit, unitList);
    return (
      <div className="grid grid-cols-[72px_minmax(0,1fr)_2rem] items-center gap-1.5">
        <Select
          style={{ width: 72 }}
          value={field?.method || undefined}
          placeholder={t('monitor.events.method')}
          options={COMPARISON_OPTIONS}
          onChange={onMethod}
        />
        <InputNumber
          className="w-full"
          controls={false}
          value={field?.value ?? null}
          placeholder={getThresholdValuePlaceholder(row.thresholdUnit)}
          onChange={(next) => onValue(typeof next === 'number' ? next : null)}
        />
        <span
          className="truncate text-xs text-[var(--color-text-3)]"
          title={unit || undefined}
        >
          {unit}
        </span>
      </div>
    );
  };

  return (
    <div className="w-full overflow-x-auto rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-4 shadow-md">
      {levelConditions.length > 0 ? (
        <div className="grid items-center gap-x-3 pb-2" style={columnStyle}>
          <span />
          {levelConditions.map((row) => (
            <ConditionHeading key={row.ref} row={row} />
          ))}
          <span />
        </div>
      ) : null}
      <div className="flex flex-col">
        {levels.map((level) => (
          <div
            key={level}
            className="grid items-center gap-x-3 border-t border-[var(--color-border-1)] py-2"
            style={columnStyle}
          >
            <span className="inline-flex items-center gap-2 text-sm text-[var(--color-text-1)]">
              <span
                className="inline-block h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: String(LEVEL_MAP[level] || 'var(--color-text-3)') }}
              />
              {t(`monitor.events.${level}`)}
            </span>
            {levelConditions.map((row) => {
              const field = (row.threshold || []).find((item) => item.level === level);
              return (
                <div key={row.ref}>
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
              type="text"
              size="small"
              className="px-0 text-[var(--color-text-3)]"
              aria-label={t('monitor.events.multiRemoveLevel')}
              icon={<MinusCircleOutlined />}
              onClick={() => onChange(removeMultiLevel(rows, level))}
            />
          </div>
        ))}
        {canAdd ? (
          <div className="pt-1">
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
          <div className={`mb-2 ${STRATEGY_HINT_TEXT_CLASS}`}>
            {t('monitor.events.multiRoleGate')}
          </div>
          <div className="flex flex-col gap-2">
            {gateConditions.map((row) => (
              <div key={row.ref} className="flex items-center gap-3">
                <div className="w-[140px] shrink-0">
                  <ConditionHeading row={row} />
                </div>
                <div className="w-[240px] shrink-0">
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
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default MultiThresholdGrid;
