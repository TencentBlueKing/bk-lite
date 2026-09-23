'use client';

import React, { useState, type ReactNode } from 'react';
import { Tooltip, Typography } from 'antd';
import MoreActionsDropdown, {
  type MoreActionsDropdownItem,
} from '@/components/more-actions-dropdown';
import SourceOriginBadge from '@/components/source-origin-badge';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';

const { Paragraph } = Typography;

export type GridEntityCardStatusTone = 'ok' | 'mute' | 'run' | 'warn' | 'error';

export interface GridEntityCardProps {
  name: string;
  description?: string;
  icon?: ReactNode;
  statusTone?: GridEntityCardStatusTone;
  statusLabel?: string;
  updatedAt?: string;
  sublineExtra?: ReactNode;
  origin?: 'builtin' | 'external';
  metaLabels?: string[];
  meta?: ReactNode;
  reserveMeta?: boolean;
  body?: ReactNode;
  headerActions?: ReactNode;
  menuItems?: MoreActionsDropdownItem[];
  footer?: 'entity' | 'none' | ReactNode;
  footerClassName?: string;
  owner?: string;
  team?: string | string[];
  ownerLabel?: string;
  teamLabel?: string;
  onClick?: () => void;
  className?: string;
  wash?: boolean;
}

const STATUS_DOT: Record<GridEntityCardStatusTone, string> = {
  ok: 'bg-[var(--color-success)]',
  warn: 'bg-[var(--color-warning)]',
  run: 'bg-[var(--color-primary)]',
  mute: 'bg-[var(--color-text-4)]',
  error: 'bg-[var(--color-fail)]',
};

export function formatTeamLabel(team: string | string[] | undefined): {
  primary: string;
  extra: number;
  full: string;
} {
  const list = (Array.isArray(team) ? team : [team])
    .map((item) => String(item || '').trim())
    .filter(Boolean);
  if (list.length === 0) return { primary: '--', extra: 0, full: '--' };
  return {
    primary: list[0],
    extra: Math.max(0, list.length - 1),
    full: list.join(', '),
  };
}

function StatusPill({
  tone,
  label,
}: {
  tone: GridEntityCardStatusTone;
  label: string;
}) {
  return (
    <span className="inline-flex h-5 shrink-0 items-center gap-1.5 rounded-full bg-[var(--color-fill-1)] px-2 text-[11px] leading-none text-[var(--color-text-2)]">
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[tone]}`} />
      {label}
    </span>
  );
}

function isCustomFooter(footer: GridEntityCardProps['footer']): footer is ReactNode {
  return footer != null && footer !== 'entity' && footer !== 'none';
}

export default function GridEntityCard({
  name,
  description,
  icon,
  statusTone,
  statusLabel,
  updatedAt,
  sublineExtra,
  origin,
  metaLabels = [],
  meta,
  reserveMeta = false,
  body,
  headerActions,
  menuItems,
  footer = 'none',
  footerClassName,
  owner = '--',
  team,
  ownerLabel,
  teamLabel,
  onClick,
  className = '',
  wash = false,
}: GridEntityCardProps) {
  const { t } = useTranslation();
  const [hover, setHover] = useState(false);
  const teamNames = formatTeamLabel(team);
  const hasSubline = Boolean(statusLabel || updatedAt || sublineExtra);
  const defaultMeta = Boolean(origin || metaLabels.length);
  const hasMeta = Boolean(meta) || defaultMeta || reserveMeta;
  const showFooter = footer !== 'none';
  const compact = !hasSubline && !hasMeta && !body && !showFooter;
  const resolvedOwnerLabel = ownerLabel || t('common.owner', '所有者');
  const resolvedTeamLabel = teamLabel || t('common.team', '团队');
  const washBackground = hover
    ? 'linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 6%, var(--color-bg-hover)) 0%, var(--color-bg-hover) 48%)'
    : 'linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 4%, var(--color-bg)) 0%, var(--color-bg) 42%)';

  return (
    <article
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      aria-label={name}
      className={`group flex h-full ${compact ? 'min-h-[144px]' : 'min-h-[168px]'} flex-col overflow-hidden rounded-lg border border-[var(--color-border-1)] transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color-mix(in_srgb,var(--color-primary)_45%,transparent)] ${
        wash ? '' : 'bg-[var(--color-bg)] hover:bg-[var(--color-bg-hover)]'
      } ${onClick ? 'cursor-pointer' : ''} ${className}`}
      style={wash ? { background: washBackground } : undefined}
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
      <div className={`flex justify-between gap-2.5 px-3.5 ${compact ? 'pt-4' : 'pt-3.5'} ${hasSubline ? 'items-start' : 'items-center'}`}>
        <div className={`flex min-w-0 flex-1 gap-3 ${hasSubline ? 'items-start' : 'items-center'}`}>
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-[var(--color-fill-1)]">
            {icon}
          </div>
          <div className="min-w-0 flex-1">
            <EllipsisWithTooltip
              text={name}
              className="truncate text-[15px] font-semibold leading-snug tracking-[-0.01em] text-[var(--color-text-1)]"
            />
            {hasSubline ? (
              <div className="mt-1 flex min-h-5 min-w-0 items-center gap-2">
                {statusLabel && statusTone ? (
                  <StatusPill tone={statusTone} label={statusLabel} />
                ) : null}
                {updatedAt ? (
                  <span className="truncate text-xs leading-5 text-[var(--color-text-3)]">
                    {updatedAt}
                  </span>
                ) : null}
                {sublineExtra}
              </div>
            ) : null}
          </div>
        </div>

        {headerActions || menuItems?.length ? (
          <div className="flex shrink-0 items-center gap-0.5" onClick={(event) => event.stopPropagation()}>
            {headerActions}
            {menuItems?.length ? (
              <MoreActionsDropdown
                items={menuItems}
                placement="bottomRight"
                stopPropagation
                buttonClassName={hover ? 'bg-[var(--color-fill-1)]' : undefined}
              />
            ) : null}
          </div>
        ) : null}
      </div>

      <div className={`flex flex-1 flex-col px-3.5 ${compact ? 'pb-4 pt-3' : 'pb-3.5 pt-2.5'} ${body ? 'gap-2' : 'gap-2.5'}`}>
        <Paragraph
          className={`!mb-0 !text-xs !leading-[1.5] !text-[var(--color-text-2)] ${body || compact ? '' : '!h-9'}`}
          ellipsis={{ rows: 2 }}
        >
          {description || '--'}
        </Paragraph>

        {hasMeta ? (
          <div className={`${body || showFooter ? '' : 'mt-auto '}flex min-h-5 flex-wrap items-center gap-1.5`}>
            {meta ?? (
              <>
                {origin ? (
                  <SourceOriginBadge
                    kind={origin}
                    className="h-5 px-1.5 text-[11px] leading-5"
                  />
                ) : null}
                {metaLabels.map((label) => (
                  <span
                    key={label}
                    className="inline-flex h-5 items-center rounded-md bg-[var(--color-fill-1)] px-1.5 text-[11px] font-normal text-[var(--color-text-3)]"
                  >
                    {label}
                  </span>
                ))}
              </>
            )}
          </div>
        ) : null}

        {body ? <div className={showFooter ? '' : 'mt-auto'}>{body}</div> : null}

        {showFooter ? (
          <div
            className={`${body ? '' : 'mt-auto '}flex border-t border-[var(--color-fill-2)] pt-2.5 text-xs text-[var(--color-text-3)] ${
              footerClassName
              || (footer === 'entity' ? 'items-center justify-between gap-2' : 'items-center justify-between gap-3')
            }`}
          >
            {footer === 'entity' ? (
              <>
                <div className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
                  <span className="text-[var(--color-text-4)]">{resolvedOwnerLabel}</span>
                  <span className="mx-1.5 text-[var(--color-text-4)]">·</span>
                  <span className="text-[var(--color-text-2)]">{owner || '--'}</span>
                </div>
                <div className="inline-flex max-w-[62%] min-w-0 items-center justify-end gap-1.5">
                  <span className="shrink-0 text-[var(--color-text-4)]">{resolvedTeamLabel}</span>
                  <span className="shrink-0 text-[var(--color-text-4)]">·</span>
                  <EllipsisWithTooltip
                    text={teamNames.primary}
                    tooltip={teamNames.extra > 0 ? teamNames.full : undefined}
                    className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[var(--color-text-2)]"
                  />
                  {teamNames.extra > 0 ? (
                    <Tooltip title={teamNames.full}>
                      <span className="h-[18px] shrink-0 rounded-full bg-[var(--color-primary-bg-active)] px-1.5 text-[11px] leading-[18px] text-[var(--color-primary)] tabular-nums">
                        +{teamNames.extra}
                      </span>
                    </Tooltip>
                  ) : null}
                </div>
              </>
            ) : isCustomFooter(footer) ? footer : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}
