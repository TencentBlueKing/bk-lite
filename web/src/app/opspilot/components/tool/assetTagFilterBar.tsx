'use client';

import React, { useEffect, useState } from 'react';
import type { TagChip } from '@/app/opspilot/utils/assetTagFilter';
import { useTranslation } from '@/utils/i18n';

const VISIBLE_TAG_COUNT = 5;

interface AssetTagFilterBarProps {
  chips: TagChip[];
  selected: string[];
  onChange: (selected: string[]) => void;
}

const chipClassName = (lit: boolean) =>
  `inline-flex h-7 shrink-0 items-center rounded-full border px-2.5 text-xs transition-colors ${
    lit
      ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg-active)] text-[var(--color-primary)]'
      : 'border-[var(--color-border-1)] bg-[var(--color-bg)] text-[var(--color-text-2)] hover:border-[var(--color-primary)]/40'
  }`;

const AssetTagFilterBar: React.FC<AssetTagFilterBarProps> = ({ chips, selected, onChange }) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const chipKey = chips.map((chip) => chip.value).join('\0');

  useEffect(() => {
    setExpanded(false);
  }, [chipKey]);

  if (!chips.length) return null;

  const toggle = (value: string) => {
    onChange(selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value]);
  };

  const showAll = () => {
    if (selected.length === 0) return;
    onChange([]);
  };

  const head = chips.slice(0, VISIBLE_TAG_COUNT);
  const rest = chips.slice(VISIBLE_TAG_COUNT);
  const selectedRest = rest.filter((chip) => selected.includes(chip.value));
  const hiddenCount = rest.length - selectedRest.length;
  const shown = expanded ? chips : [...head, ...selectedRest];

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        aria-pressed={selected.length === 0}
        className={chipClassName(selected.length === 0)}
        onClick={showAll}
      >
        {t('tool.allTags', '全部')}
      </button>
      {shown.map((chip) => {
        const lit = selected.includes(chip.value);
        return (
          <button
            key={chip.value}
            type="button"
            aria-pressed={lit}
            className={chipClassName(lit)}
            onClick={() => toggle(chip.value)}
          >
            {chip.label}
          </button>
        );
      })}
      {(expanded || hiddenCount > 0) && rest.length > 0 ? (
        <button
          type="button"
          aria-expanded={expanded}
          className={chipClassName(expanded)}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded
            ? t('tool.collapseTags', '收起')
            : t('tool.moreTags', '更多 {count}', { count: hiddenCount })}
        </button>
      ) : null}
    </div>
  );
};

export default AssetTagFilterBar;
