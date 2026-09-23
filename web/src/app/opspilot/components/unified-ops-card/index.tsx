'use client';

/**
 * OpsPilot Look B 统一列表卡 — 视觉底盘走 shared grid-entity-card。
 * 置顶、厂商图标、模型色、供应商/记忆底栏仍留在本包装层。
 */

import React, { useMemo, type ReactNode } from 'react';
import { Dropdown, Switch, Tooltip } from 'antd';
import { MoreOutlined, PushpinFilled, PushpinOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import GridEntityCard from '@/components/grid-entity-card';
import { useTranslation } from '@/utils/i18n';

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
  const st = status ? STATUS_META[status] : null;
  const statusText = useMemo(() => {
    if (!st) {
      return undefined;
    }
    return statusLabel ?? t(st.messageId);
  }, [st, statusLabel, t]);

  const iconNode = vendorIcon ? (
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
  ) : null;

  const metaNode = (
    <>
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
    </>
  );

  let footerSlot: React.ComponentProps<typeof GridEntityCard>['footer'] = 'entity';
  if (footer === 'none') {
    footerSlot = 'none';
  } else if (footer === 'provider') {
    footerSlot = (
      <>
        <span className="text-[var(--color-text-4)]">
          {t('unifiedCard.modelCount', undefined, { count: modelCount ?? 0 })}
        </span>
        <span onClick={(event) => event.stopPropagation()}>
          <Switch
            size="small"
            checked={enabled ?? false}
            loading={switchLoading}
            aria-label={t('unifiedCard.enableAria', undefined, { name })}
            onChange={(checked) => onEnabledChange?.(checked)}
          />
        </span>
      </>
    );
  } else if (footer === 'memory') {
    footerSlot = (
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
    );
  }

  const headerActions = (showPin || menuOverlay) ? (
    <>
      {showPin ? (
        <Tooltip title={pinned ? t('common.unpin') : t('common.pin')}>
          <button
            type="button"
            aria-label={pinned ? t('common.unpin') : t('common.pin')}
            className="grid h-7 w-7 place-items-center rounded-md border-0 bg-transparent text-[var(--color-text-4)] group-hover:text-[var(--color-text-3)]"
            style={{ color: pinned ? 'var(--color-primary)' : undefined }}
            onClick={(event) => {
              event.stopPropagation();
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
            className="grid h-7 w-7 place-items-center rounded-md border-0 bg-transparent text-[var(--color-text-3)] group-hover:bg-[var(--color-fill-1)]"
            onClick={(event) => event.stopPropagation()}
          >
            <MoreOutlined style={{ fontSize: 14 }} />
          </button>
        </Dropdown>
      ) : null}
    </>
  ) : null;

  return (
    <GridEntityCard
      name={name}
      description={description}
      icon={iconNode}
      statusTone={st?.tone}
      statusLabel={statusText}
      updatedAt={updatedAt}
      meta={metaNode}
      reserveMeta
      headerActions={headerActions}
      footer={footerSlot}
      owner={owner}
      team={team}
      ownerLabel={t('unifiedCard.owner')}
      teamLabel={t('unifiedCard.team')}
      onClick={onClick}
      className={className}
      wash
    />
  );
}
