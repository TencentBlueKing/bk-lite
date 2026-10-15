'use client';

import { InputNumber } from 'antd';

import { useTranslation } from '@/utils/i18n';

const MIB = 1024 * 1024;

export interface BudgetForm {
  requestsPerMinute: number | null;
  eventsPerMinute: number | null;
  compressedMiB: number | null;
  decompressedMiB: number | null;
};

export const DEFAULT_BUDGET_FORM: BudgetForm = {
  requestsPerMinute: 6000,
  eventsPerMinute: 20000,
  compressedMiB: 32,
  decompressedMiB: 128,
};

const LIMITS = {
  requestsPerMinute: 120_000,
  eventsPerMinute: 200_000,
  compressedMiB: 256,
  decompressedMiB: 1024,
} as const;

function wholeMiB(bytes: number | undefined, fallback: number): number {
  if (bytes == null || !Number.isFinite(bytes) || bytes <= 0) return fallback;
  return Math.max(1, Math.round(bytes / MIB));
}

export function budgetFormFromApi(budgets?: Record<string, number>): BudgetForm {
  if (!budgets) return { ...DEFAULT_BUDGET_FORM };
  return {
    requestsPerMinute: budgets.requestsPerMinute ?? DEFAULT_BUDGET_FORM.requestsPerMinute,
    eventsPerMinute: budgets.eventsPerMinute ?? DEFAULT_BUDGET_FORM.eventsPerMinute,
    compressedMiB: wholeMiB(budgets.compressedBytesPerMinute, DEFAULT_BUDGET_FORM.compressedMiB!),
    decompressedMiB: wholeMiB(
      budgets.decompressedBytesPerMinute,
      DEFAULT_BUDGET_FORM.decompressedMiB!,
    ),
  };
}

export function budgetPayload(form: BudgetForm): Record<string, number> | 'incomplete' | 'order' {
  const requests = form.requestsPerMinute;
  const events = form.eventsPerMinute;
  const compressed = form.compressedMiB;
  const decompressed = form.decompressedMiB;
  if (
    requests == null ||
    events == null ||
    compressed == null ||
    decompressed == null ||
    !Number.isInteger(requests) ||
    !Number.isInteger(events) ||
    !Number.isInteger(compressed) ||
    !Number.isInteger(decompressed)
  ) {
    return 'incomplete';
  }
  if (decompressed < compressed) return 'order';
  return {
    requestsPerMinute: requests,
    eventsPerMinute: events,
    compressedBytesPerMinute: compressed * MIB,
    decompressedBytesPerMinute: decompressed * MIB,
  };
}

export function BudgetFields({
  value,
  onChange,
  disabled = false,
}: {
  value: BudgetForm;
  onChange: (next: BudgetForm) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const fields: Array<{
    key: keyof BudgetForm;
    label: string;
    max: number;
  }> = [
    {
      key: 'requestsPerMinute',
      label: t('rum.budgets.requests', '请求数'),
      max: LIMITS.requestsPerMinute,
    },
    {
      key: 'eventsPerMinute',
      label: t('rum.budgets.events', '事件数'),
      max: LIMITS.eventsPerMinute,
    },
    {
      key: 'compressedMiB',
      label: t('rum.budgets.compressed', '压缩体积（MiB）'),
      max: LIMITS.compressedMiB,
    },
    {
      key: 'decompressedMiB',
      label: t('rum.budgets.decompressed', '解压体积（MiB）'),
      max: LIMITS.decompressedMiB,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {fields.map((field) => (
        <label key={field.key} className="block text-xs text-[var(--color-text-2)]">
          <span className="mb-1 block">{field.label}</span>
          <InputNumber
            className="w-full"
            min={1}
            max={field.max}
            precision={0}
            disabled={disabled}
            value={value[field.key]}
            onChange={(next) => onChange({ ...value, [field.key]: next })}
          />
        </label>
      ))}
    </div>
  );
}
