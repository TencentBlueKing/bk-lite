'use client';

import React from 'react';
import { Radio } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ConditionSource } from './formulaExpressionUtils';
import { STRATEGY_HINT_TEXT_CLASS } from './alertDurationFields';

interface MetricConditionCardProps {
  showSourceSwitch?: boolean;
  source?: ConditionSource;
  onSourceChange?: (source: ConditionSource) => void;
  note?: string;
  children: React.ReactNode;
}

const MetricConditionCard: React.FC<MetricConditionCardProps> = ({
  showSourceSwitch = false,
  source = 'metric',
  onSourceChange,
  note,
  children
}) => {
  const { t } = useTranslation();

  return (
    <div className="mx-3 mt-3 rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-3">
      {showSourceSwitch ? (
        <Radio.Group
          className="mb-3"
          optionType="button"
          size="small"
          value={source}
          onChange={(event) => onSourceChange?.(event.target.value)}
          options={[
            {
              label: t('monitor.events.conditionSourceMetric'),
              value: 'metric'
            },
            {
              label: t('monitor.events.conditionSourceFormula'),
              value: 'formula'
            }
          ]}
        />
      ) : null}
      {note ? (
        <p className={`mb-2 ${STRATEGY_HINT_TEXT_CLASS}`}>{note}</p>
      ) : null}
      <div className="flex flex-col gap-3">{children}</div>
    </div>
  );
};

export default MetricConditionCard;
