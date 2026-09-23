'use client';

import { Button, Input } from 'antd';
import { MinusOutlined, PlusOutlined } from '@ant-design/icons';

import { useTranslation } from '@/utils/i18n';

const MAX_ORIGINS = 20;

export function OriginEditor({
  origins,
  onChange,
  disabled = false,
}: {
  origins: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const rows = origins.length > 0 ? origins : [''];
  const atMax = rows.length >= MAX_ORIGINS;

  return (
    <div className="space-y-2">
      {rows.map((origin, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            value={origin}
            placeholder={t('rum.origin.placeholder', 'https://app.example.com')}
            disabled={disabled}
            onChange={(event) =>
              onChange(rows.map((row, i) => (i === index ? event.target.value : row)))
            }
          />
          <Button
            type="default"
            size="small"
            className="size-8 shrink-0 px-0"
            icon={<MinusOutlined />}
            disabled={disabled || rows.length <= 1}
            onClick={() => onChange(rows.filter((_, i) => i !== index))}
            aria-label={t('rum.origin.remove', '删除 Origin')}
          />
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="link"
          size="small"
          className="h-auto px-0"
          icon={<PlusOutlined />}
          disabled={disabled || atMax}
          onClick={() => onChange([...rows, ''])}
        >
          {t('rum.origin.add', '添加 Origin')}
        </Button>
        <span className="text-xs text-[var(--color-text-3)]">
          {atMax
            ? t('rum.origin.maxHint', '已达上限 {max} 个', { max: MAX_ORIGINS })
            : t('rum.origin.countHint', '{count} / {max}', {
              count: rows.length,
              max: MAX_ORIGINS,
            })}
        </span>
      </div>
    </div>
  );
}

export function OriginChips({ origins }: { origins: string[] }) {
  if (origins.length === 0) {
    return <p className="text-xs text-[var(--color-text-3)]">—</p>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {origins.map((origin) => (
        <code
          key={origin}
          className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-2)] px-2 py-0.5 font-mono text-xs text-[var(--color-text-1)]"
        >
          {origin}
        </code>
      ))}
    </div>
  );
}
