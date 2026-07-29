import React from 'react';
import { useTranslation } from '@/utils/i18n';

export interface SourceOriginBadgeProps {
  kind: 'builtin' | 'external' | 'custom' | 'imported';
  label?: React.ReactNode;
  mode?: 'pill' | 'inline';
  className?: string;
  parenthesized?: boolean;
}

const STYLE_BY_KIND = {
  builtin: {
    text: 'var(--color-primary)',
    background: 'color-mix(in srgb, var(--color-primary) 12%, transparent)',
  },
  external: {
    text: 'var(--color-success)',
    background: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
  },
  custom: {
    text: 'var(--color-text-2)',
    background: 'color-mix(in srgb, var(--color-fill-5) 30%, transparent)',
  },
  imported: {
    text: '#722ed1',
    background: 'color-mix(in srgb, #722ed1 12%, transparent)',
  },
} as const;

const SourceOriginBadge: React.FC<SourceOriginBadgeProps> = ({
  kind,
  label,
  mode = 'pill',
  className = '',
  parenthesized = false,
}) => {
  const { t } = useTranslation();
  const resolvedLabel = label || {
    builtin: t('common.builtIn'),
    external: t('common.externalApp'),
    custom: t('common.custom'),
    imported: 'Imported',
  }[kind];

  if (mode === 'inline') {
    const inlineLabel = parenthesized ? `(${resolvedLabel})` : resolvedLabel;
    return (
      <span
        className={`text-[10px] text-[var(--color-text-3)] ${className}`.trim()}
      >
        {inlineLabel}
      </span>
    );
  }

  const palette = STYLE_BY_KIND[kind];

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium leading-4 ${className}`.trim()}
      style={{
        color: palette.text,
        backgroundColor: palette.background,
      }}
    >
      {resolvedLabel}
    </span>
  );
};

export default SourceOriginBadge;
