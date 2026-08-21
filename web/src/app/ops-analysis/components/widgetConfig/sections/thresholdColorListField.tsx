import React, { useCallback } from 'react';
import { ThresholdColorConfigSection } from '@/app/ops-analysis/components/thresholdColorConfigSection';
import type { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';

interface ThresholdColorListFieldProps {
  t: (key: string, defaultMessage?: string) => string;
  label: React.ReactNode;
  extra?: React.ReactNode;
  value?: ThresholdColorConfig[];
  onChange?: (next: ThresholdColorConfig[]) => void;
}

const sortByValueDesc = (items: ThresholdColorConfig[]) =>
  [...items].sort((a, b) => parseFloat(b.value) - parseFloat(a.value));

const nextUniqueValue = (existing: number[], preferred: number) => {
  let next = preferred;
  while (existing.includes(next)) {
    next += 1;
  }
  return next;
};

/** Ant Design Form.Item 受控：空列表表示未配阈值，画布保持默认文字色。 */
export const ThresholdColorListField: React.FC<ThresholdColorListFieldProps> = ({
  t,
  label,
  extra,
  value,
  onChange,
}) => {
  const thresholds = Array.isArray(value) ? value : [];

  const commit = useCallback(
    (next: ThresholdColorConfig[]) => {
      onChange?.(next);
    },
    [onChange],
  );

  const handleThresholdChange = useCallback(
    (index: number, field: 'value' | 'color', nextValue: string | number) => {
      const next = [...thresholds];
      next[index] = {
        ...next[index],
        [field]: field === 'value' ? String(nextValue) : String(nextValue),
      };
      commit(next);
    },
    [commit, thresholds],
  );

  const handleThresholdBlur = useCallback(
    (index: number, raw: number | null) => {
      const next = [...thresholds];
      if (raw === null || raw === undefined) {
        next[index] = { ...next[index], value: '0' };
        commit(sortByValueDesc(next));
        return;
      }
      const existing = thresholds
        .map((item, itemIndex) =>
          itemIndex === index ? Number.NaN : parseFloat(item.value),
        )
        .filter((item) => Number.isFinite(item));
      const unique = nextUniqueValue(existing, Number(raw));
      next[index] = { ...next[index], value: String(unique) };
      commit(sortByValueDesc(next));
    },
    [commit, thresholds],
  );

  const addThreshold = useCallback(
    (afterIndex?: number) => {
      const existing = thresholds
        .map((item) => parseFloat(item.value))
        .filter((item) => Number.isFinite(item));
      let preferred = 0;
      if (afterIndex !== undefined && afterIndex >= 0) {
        const currentValue = parseFloat(thresholds[afterIndex]?.value || '0');
        const nextValue =
          afterIndex + 1 < thresholds.length
            ? parseFloat(thresholds[afterIndex + 1]?.value || '0')
            : 0;
        if (currentValue - nextValue > 1) {
          preferred = Math.floor((currentValue + nextValue) / 2);
        } else {
          preferred = Math.max(currentValue - 1, nextValue);
        }
      } else if (existing.length > 0) {
        preferred = Math.max(...existing) + 10;
      }
      const created: ThresholdColorConfig = {
        color: '#dc2626',
        value: String(nextUniqueValue(existing, preferred)),
      };
      commit(sortByValueDesc([...thresholds, created]));
    },
    [commit, thresholds],
  );

  const removeThreshold = useCallback(
    (index: number) => {
      commit(thresholds.filter((_, itemIndex) => itemIndex !== index));
    },
    [commit, thresholds],
  );

  return (
    <ThresholdColorConfigSection
      t={t}
      label={label}
      extra={extra}
      thresholdColors={thresholds}
      onThresholdChange={handleThresholdChange}
      onThresholdBlur={handleThresholdBlur}
      onAddThreshold={addThreshold}
      onRemoveThreshold={removeThreshold}
      allowEmpty
    />
  );
};
