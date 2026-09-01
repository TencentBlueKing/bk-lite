'use client';

import React from 'react';
import { Popover } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  contextUsagePercent,
  formatContextTokens,
  type ContextUsageSegmentId,
  type LlmContextUsage,
} from './llmContextUsage';

const SEGMENT_BAR_CLASS: Record<ContextUsageSegmentId, string> = {
  system: 'bg-[var(--color-text-4)]',
  tools: 'bg-[var(--color-primary)]',
  skills: 'bg-[var(--color-warning)]',
  wiki: 'bg-[var(--color-success)]',
  summary: 'bg-[var(--color-fail)]',
  conversation: 'bg-[color-mix(in_srgb,var(--color-primary)_45%,var(--color-warning))]',
};

const SEGMENT_LABEL_KEY: Record<ContextUsageSegmentId, string> = {
  system: 'chat.contextUsage.system',
  tools: 'chat.contextUsage.tools',
  skills: 'chat.contextUsage.skills',
  wiki: 'chat.contextUsage.wiki',
  summary: 'chat.contextUsage.summary',
  conversation: 'chat.contextUsage.conversation',
};

function ringStroke(percent: number): string {
  if (percent >= 90) {
    return 'var(--color-fail)';
  }
  if (percent >= 75) {
    return 'var(--color-warning)';
  }
  return 'var(--color-primary)';
}

function UsageRingGlyph({ percent }: { percent: number }) {
  const radius = 7;
  const circumference = 2 * Math.PI * radius;
  const filled = (Math.min(100, Math.max(0, percent)) / 100) * circumference;
  return (
    <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true" className="shrink-0">
      <circle
        cx="10"
        cy="10"
        r={radius}
        fill="none"
        stroke="var(--color-border-2)"
        strokeWidth="2.4"
      />
      <circle
        cx="10"
        cy="10"
        r={radius}
        fill="none"
        strokeWidth="2.4"
        strokeLinecap="round"
        style={{
          stroke: ringStroke(percent),
          strokeDasharray: `${filled} ${circumference}`,
        }}
        transform="rotate(-90 10 10)"
      />
    </svg>
  );
}

function UsagePopoverBody({ usage }: { usage: LlmContextUsage | null }) {
  const { t } = useTranslation();
  if (!usage) {
    return (
      <div className="flex w-72 flex-col gap-2">
        <div className="text-sm font-medium text-[var(--color-text-1)]">{t('chat.contextUsage.title')}</div>
        <p className="m-0 text-xs leading-5 text-[var(--color-text-3)]">{t('chat.contextUsage.waitingHint')}</p>
      </div>
    );
  }
  const percent = contextUsagePercent(usage);
  const nearCap = percent >= 90;
  const pastCompact =
    usage.compactionThresholdTokens > 0 && usage.packetTokens >= usage.compactionThresholdTokens;

  return (
    <div className="flex w-80 flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-[var(--color-text-1)]">{t('chat.contextUsage.title')}</div>
          <div className="text-xs text-[var(--color-text-3)]">{t('chat.contextUsage.packetHint')}</div>
        </div>
        <div className="text-right text-xs text-[var(--color-text-2)]">
          {percent}% {t('chat.contextUsage.used')}
          <div>
            {t('chat.contextUsage.about')} {formatContextTokens(usage.packetTokens)} /{' '}
            {formatContextTokens(usage.inputWorkingTokens)}
          </div>
        </div>
      </div>
      <div className="flex h-2 w-full overflow-hidden rounded-sm bg-[var(--color-fill-2)]">
        {usage.segments.map((segment) => (
          <div
            key={segment.id}
            className={`h-full min-w-0 ${SEGMENT_BAR_CLASS[segment.id]}`}
            style={{ flexGrow: segment.tokens, flexBasis: 0 }}
          />
        ))}
      </div>
      <div className="flex flex-col gap-1.5">
        {usage.segments.map((segment) => (
          <div key={segment.id} className="flex items-center gap-2 text-xs text-[var(--color-text-2)]">
            <span className={`h-2.5 w-2.5 shrink-0 rounded-sm ${SEGMENT_BAR_CLASS[segment.id]}`} />
            <span className="flex-1">{t(SEGMENT_LABEL_KEY[segment.id])}</span>
            <span className="text-[var(--color-text-3)]">{formatContextTokens(segment.tokens)}</span>
          </div>
        ))}
      </div>
      <p className="m-0 text-xs leading-5 text-[var(--color-text-3)]">
        {t(
          'chat.contextUsage.budgetHint',
          '分母是输入工作预算（模型窗口 {window}）。压缩线约 {compact}。',
          {
            window: formatContextTokens(usage.windowTokens || usage.inputWorkingTokens),
            compact: formatContextTokens(usage.compactionThresholdTokens),
          }
        )}
      </p>
      {usage.compacted || pastCompact ? (
        <p className="m-0 text-xs leading-5 text-[var(--color-text-2)]">{t('chat.contextUsage.compactedHint')}</p>
      ) : null}
      {nearCap ? (
        <p className="m-0 text-xs leading-5 text-[var(--color-warning)]">{t('chat.contextUsage.nearCapHint')}</p>
      ) : null}
    </div>
  );
}

export default function ContextUsageRing({ usage }: { usage: LlmContextUsage | null }) {
  const { t } = useTranslation();
  const percent = usage ? contextUsagePercent(usage) : 0;
  return (
    <Popover
      trigger="click"
      placement="topRight"
      arrow={false}
      content={<UsagePopoverBody usage={usage} />}
    >
      <button
        type="button"
        className="inline-flex h-8 items-center gap-1.5 rounded px-1.5 text-xs text-[var(--color-text-2)] hover:bg-[var(--color-fill-2)]"
        title={t('chat.contextUsage.title')}
        aria-label={`${percent}% ${t('chat.contextUsage.title')}`}
      >
        <UsageRingGlyph percent={percent} />
        <span>{percent}%</span>
      </button>
    </Popover>
  );
}
