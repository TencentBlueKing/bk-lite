'use client';

/**
 * OpsPilot Look B 统一列表卡 — 与 Storybook UnifiedOpsCard 解剖一致。
 */

import React, { useMemo, useState, type ReactNode } from 'react';
import { Dropdown, Switch, Tooltip, Typography } from 'antd';
import { MoreOutlined, PushpinFilled, PushpinOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';

const { Paragraph } = Typography;

export type UnifiedOpsCardFooter = 'entity' | 'provider' | 'memory' | 'none';

export type UnifiedOpsCardStatus =
  | 'online'
  | 'offline'
  | 'ready'
  | 'building'
  | 'enabled'
  | 'disabled';

export interface UnifiedOpsCardProps {
  name: string;
  description: string;
  icon?: string;
  vendorIcon?: string;
  status?: UnifiedOpsCardStatus;
  statusLabel?: string;
  updatedAt?: string;
  meta?: string[];
  pinned?: boolean;
  showPin?: boolean;
  footer?: UnifiedOpsCardFooter;
  owner?: string;
  team?: string | string[];
  footerRight?: string;
  modelCount?: number;
  enabled?: boolean;
  switchLoading?: boolean;
  menuOverlay?: ReactNode;
  onClick?: () => void;
  onPinClick?: () => void;
  onEnabledChange?: (enabled: boolean) => void;
  className?: string;
}

function formatTeamLabel(team: string | string[]): {
  primary: string;
  extra: number;
  full: string;
} {
  const list = (Array.isArray(team) ? team : [team]).map((t) => String(t).trim()).filter(Boolean);
  if (list.length === 0) return { primary: '--', extra: 0, full: '--' };
  return {
    primary: list[0],
    extra: Math.max(0, list.length - 1),
    full: list.join(','),
  };
}

function metaTagBg(hue: string) {
  return `color-mix(in srgb, ${hue} 13%, var(--color-bg))`;
}

const metaNeutral = {
  color: 'var(--color-text-3)',
  background: 'var(--color-fill-1)',
} as const;

function resolveMetaTagTone(label: string): {
  color: string;
  background: string;
  fontWeight: number;
} {
  const key = label.trim().toLowerCase();
  if (/记忆条数/.test(label)) return { ...metaNeutral, fontWeight: 400 };
  if (/^\d+\s*(docs|models|条)/.test(key)) return { ...metaNeutral, fontWeight: 400 };

  const modelFamilies: Array<{ match: RegExp; color: string }> = [
    { match: /^(gpt-|o[1-9]|chatgpt|openai)/, color: 'var(--color-success)' },
    { match: /^(claude|anthropic)/, color: '#d97706' },
    { match: /^deepseek/, color: '#7c3aed' },
    { match: /^(kimi|moonshot)/, color: '#2563eb' },
    { match: /^(qwen|qwq|tongyi)/, color: '#0891b2' },
    { match: /^minimax/, color: '#db2777' },
    { match: /^(glm|chatglm|zhipu)/, color: '#4f46e5' },
    { match: /^(ernie|wenxin|baidu)/, color: '#1d4ed8' },
    { match: /^(llama|mistral|gemma)/, color: '#0d9488' },
    { match: /^(gemini|palm)/, color: '#ea580c' },
  ];
  for (const family of modelFamilies) {
    if (family.match.test(key)) {
      return { color: family.color, background: metaTagBg(family.color), fontWeight: 500 };
    }
  }

  const semantic: Record<string, { color: string; background: string; fontWeight: number }> = {
    pilot: { color: 'var(--color-primary)', background: metaTagBg('var(--color-primary)'), fontWeight: 500 },
    chatflow: { color: 'var(--color-primary)', background: metaTagBg('var(--color-primary)'), fontWeight: 500 },
    lobechat: { color: 'var(--color-primary)', background: metaTagBg('var(--color-primary)'), fontWeight: 500 },
    rag: { color: 'var(--color-primary)', background: metaTagBg('var(--color-primary)'), fontWeight: 500 },
    'q&a': { color: 'var(--color-primary)', background: metaTagBg('var(--color-primary)'), fontWeight: 500 },
    mcp: { color: 'var(--color-primary)', background: metaTagBg('var(--color-primary)'), fontWeight: 500 },
    团队: { color: 'var(--color-primary)', background: metaTagBg('var(--color-primary)'), fontWeight: 500 },
    个人: { color: 'var(--color-primary)', background: metaTagBg('var(--color-primary)'), fontWeight: 500 },
    上线: { color: 'var(--color-success)', background: metaTagBg('var(--color-success)'), fontWeight: 400 },
    下线: { color: 'var(--color-text-3)', background: 'var(--color-fill-1)', fontWeight: 400 },
    online: { color: 'var(--color-success)', background: metaTagBg('var(--color-success)'), fontWeight: 400 },
    offline: { color: 'var(--color-text-3)', background: 'var(--color-fill-1)', fontWeight: 400 },
  };
  if (semantic[key]) return semantic[key];

  // 未识别模型名：按字符串稳定散列到色板，保证「不同模型不同色」
  if (/[a-z]/.test(key) && (key.includes('-') || key.includes('_') || /\d/.test(key))) {
    const palette = [
      'var(--color-primary)',
      'var(--color-success)',
      '#7c3aed',
      '#0891b2',
      '#db2777',
      '#d97706',
      '#4f46e5',
      '#0d9488',
    ];
    let hash = 0;
    for (let i = 0; i < key.length; i += 1) {
      hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
    }
    const color = palette[hash % palette.length];
    return { color, background: metaTagBg(color), fontWeight: 500 };
  }

  return { ...metaNeutral, fontWeight: 400 };
}

function StatusPill({
  tone,
  label,
}: {
  tone: 'ok' | 'mute' | 'run' | 'warn';
  label: string;
}) {
  const color =
    tone === 'ok'
      ? 'var(--color-success)'
      : tone === 'warn'
        ? 'var(--color-warning)'
        : tone === 'run'
          ? 'var(--color-primary)'
          : 'var(--color-text-4)';
  return (
    <span className="inline-flex h-5 shrink-0 items-center gap-1.5 rounded-full bg-[var(--color-fill-1)] px-2 text-[11px] leading-none text-[var(--color-text-2)]">
      <span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

const STATUS_META: Record<
  UnifiedOpsCardStatus,
  { messageId: string; tone: 'ok' | 'mute' | 'run' | 'warn' }
> = {
  online: { messageId: 'unifiedCard.status.online', tone: 'ok' },
  offline: { messageId: 'unifiedCard.status.offline', tone: 'mute' },
  ready: { messageId: 'unifiedCard.status.ready', tone: 'ok' },
  building: { messageId: 'unifiedCard.status.building', tone: 'run' },
  enabled: { messageId: 'unifiedCard.status.enabled', tone: 'ok' },
  disabled: { messageId: 'unifiedCard.status.disabled', tone: 'mute' },
};

export default function UnifiedOpsCard({
  name,
  description,
  icon,
  vendorIcon,
  status,
  statusLabel,
  updatedAt,
  meta = [],
  pinned,
  showPin = false,
  footer = 'entity',
  owner = '--',
  team = '--',
  footerRight,
  modelCount,
  enabled,
  switchLoading,
  menuOverlay,
  onClick,
  onPinClick,
  onEnabledChange,
  className = '',
}: UnifiedOpsCardProps) {
  const { t } = useTranslation();
  const [hover, setHover] = useState(false);
  const teamLabel = formatTeamLabel(team);
  const st = status ? STATUS_META[status] : null;
  const statusText = useMemo(() => {
    if (!st) {
      return undefined;
    }
    return statusLabel ?? t(st.messageId);
  }, [st, statusLabel, t]);
  const hasSubline = Boolean(statusText || updatedAt);
  const wash = hover
    ? 'linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 6%, var(--color-bg-hover)) 0%, var(--color-bg-hover) 48%)'
    : 'linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 4%, var(--color-bg)) 0%, var(--color-bg) 42%)';

  return (
    <article
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      aria-label={name}
      className={`flex h-full min-h-[168px] cursor-pointer flex-col overflow-hidden rounded-lg border border-[var(--color-border-1)] transition-[background,border-color] duration-160 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color-mix(in_srgb,var(--color-primary)_45%,transparent)] ${className}`}
      style={{ background: wash }}
      onClick={onClick}
      onKeyDown={(event) => {
        if (!onClick) return;
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div
        className={`flex justify-between gap-2.5 px-3.5 pt-3.5 ${
          hasSubline ? 'items-start' : 'items-center'
        }`}
      >
        <div
          className={`flex min-w-0 flex-1 gap-3 ${
            hasSubline ? 'items-start' : 'items-center'
          }`}
        >
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-[var(--color-fill-1)]">
            {vendorIcon ? (
              <img
                src={`/app/models/${vendorIcon}.svg`}
                alt=""
                width={22}
                height={22}
                className="object-contain"
                onError={(event) => {
                  event.currentTarget.style.display = 'none';
                }}
              />
            ) : icon ? (
              <Icon type={icon} className="text-xl text-[var(--color-primary)]" />
            ) : null}
          </div>
          <div className="min-w-0 flex-1">
            <Tooltip title={name}>
              <div className="truncate text-[15px] font-semibold leading-snug tracking-[-0.01em] text-[var(--color-text-1)]">
                {name}
              </div>
            </Tooltip>
            {hasSubline ? (
              <div className="mt-1 flex min-h-5 min-w-0 items-center gap-2">
                {st && statusText ? (
                  <StatusPill tone={st.tone} label={statusText} />
                ) : null}
                {updatedAt ? (
                  <span className="truncate text-xs leading-5 text-[var(--color-text-3)]">
                    {updatedAt}
                  </span>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        <div className="flex shrink-0 gap-0.5" onClick={(e) => e.stopPropagation()}>
          {showPin ? (
            <Tooltip title={pinned ? t('common.unpin') : t('common.pin')}>
              <button
                type="button"
                aria-label={pinned ? t('common.unpin') : t('common.pin')}
                className="grid h-7 w-7 place-items-center rounded-md border-0 bg-transparent"
                style={{ color: pinned ? 'var(--color-primary)' : 'var(--color-text-4)' }}
                onClick={(e) => {
                  e.stopPropagation();
                  onPinClick?.();
                }}
              >
                {pinned ? (
                  <PushpinFilled style={{ fontSize: 12 }} />
                ) : (
                  <PushpinOutlined style={{ fontSize: 12 }} />
                )}
              </button>
            </Tooltip>
          ) : null}
          {menuOverlay ? (
            <Dropdown overlay={menuOverlay as React.ReactElement} trigger={['click']} placement="bottomRight">
              <button
                type="button"
                aria-label={t('unifiedCard.moreActions')}
                className="grid h-7 w-7 place-items-center rounded-md border-0 text-[var(--color-text-3)]"
                style={{ background: hover ? 'var(--color-fill-1)' : 'transparent' }}
                onClick={(e) => e.stopPropagation()}
              >
                <MoreOutlined style={{ fontSize: 14 }} />
              </button>
            </Dropdown>
          ) : null}
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-2.5 px-3.5 pb-3.5 pt-2.5">
        <Paragraph
          className="!mb-0 !h-9 !text-xs !leading-[1.5] !text-[var(--color-text-2)]"
          ellipsis={{ rows: 2 }}
        >
          {description || '--'}
        </Paragraph>

        <div className="flex min-h-5 flex-wrap gap-1.5">
          {meta.map((label) => {
            const tone = resolveMetaTagTone(label);
            return (
              <span
                key={label}
                className="inline-flex h-5 items-center rounded-md px-1.5 text-[11px]"
                style={{
                  color: tone.color,
                  background: tone.background,
                  fontWeight: tone.fontWeight,
                }}
              >
                {label}
              </span>
            );
          })}
        </div>

        {footer === 'none' ? null : (
          <div className="mt-auto flex items-center justify-between gap-3 border-t border-[var(--color-fill-2)] pt-2.5 text-xs text-[var(--color-text-3)]">
            {footer === 'provider' ? (
              <>
                <span className="text-[var(--color-text-4)]">
                  {t('unifiedCard.modelCount', undefined, { count: modelCount ?? 0 })}
                </span>
                <span onClick={(e) => e.stopPropagation()}>
                  <Switch
                    size="small"
                    checked={enabled ?? false}
                    loading={switchLoading}
                    aria-label={t('unifiedCard.enableAria', undefined, { name })}
                    onChange={(checked) => onEnabledChange?.(checked)}
                  />
                </span>
              </>
            ) : footer === 'memory' ? (
              <>
                <div className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
                  <span className="text-[var(--color-text-4)]">{t('unifiedCard.owner')}</span>
                  <span className="mx-1.5 text-[var(--color-text-4)]">·</span>
                  <span className="text-[var(--color-text-2)]">{owner}</span>
                </div>
                <span className="max-w-[62%] overflow-hidden text-ellipsis whitespace-nowrap text-right text-[var(--color-text-4)]">
                  {footerRight ?? '--'}
                </span>
              </>
            ) : (
              <>
                <div className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
                  <span className="text-[var(--color-text-4)]">{t('unifiedCard.owner')}</span>
                  <span className="mx-1.5 text-[var(--color-text-4)]">·</span>
                  <span className="text-[var(--color-text-2)]">{owner || '--'}</span>
                </div>
                <Tooltip title={teamLabel.full}>
                  <div className="inline-flex max-w-[62%] min-w-0 items-center justify-end gap-1.5">
                    <span className="shrink-0 text-[var(--color-text-4)]">{t('unifiedCard.team')}</span>
                    <span className="shrink-0 text-[var(--color-text-4)]">·</span>
                    <span className="overflow-hidden text-ellipsis whitespace-nowrap text-[var(--color-text-2)]">
                      {teamLabel.primary}
                    </span>
                    {teamLabel.extra > 0 ? (
                      <span className="h-[18px] shrink-0 rounded-full bg-[var(--color-primary-bg-active)] px-1.5 text-[11px] leading-[18px] text-[var(--color-primary)] tabular-nums">
                        +{teamLabel.extra}
                      </span>
                    ) : null}
                  </div>
                </Tooltip>
              </>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
