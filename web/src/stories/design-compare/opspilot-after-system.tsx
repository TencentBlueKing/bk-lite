'use client';

/**
 * OpsPilot After visual system — token-aligned craft.
 *
 * Surfaces follow web/DESIGN.md:
 * - page: --color-background-body
 * - panel/card: --color-bg + soft edge (--color-border-1, never currentColor fallback black)
 * - muted strip / chips: --color-fill-1 (no nested border when inside a bordered card)
 * - dividers: --color-fill-2 hairline (lighter than outer edge)
 * - flat by default; hover via background, not heavy outline
 * - all colors from theme CSS vars (light/dark via html.light / html.dark)
 */

import { useState, type CSSProperties, type ReactNode } from 'react';
import {
  Button,
  Dropdown,
  Input,
  Progress,
  Segmented,
  Space,
  Switch,
  Tooltip,
  Typography,
} from 'antd';
import {
  AppstoreOutlined,
  MoreOutlined,
  PlusOutlined,
  PushpinFilled,
  PushpinOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import Icon from '@/components/icon';

const { Text, Paragraph } = Typography;

/**
 * Soft edge tokens — outer frames use border-1 (subtle), not --color-border
 * which reads too heavy next to quiet card content.
 * Fallbacks avoid invalid var() → currentColor (near-black) when tokens lag.
 */
export const afterSys = {
  pagePad: 20,
  gap: 12,
  radius: 8,
  radiusSm: 6,
  cardMin: 292,
  /** Soft outer panel / card edge */
  border: '1px solid var(--color-border-1, #edeff3)',
  /** Quieter internal hairline */
  divider: '1px solid var(--color-fill-2, #f4f5f8)',
  /** alias */
  borderSoft: '1px solid var(--color-fill-2, #f4f5f8)',
  bg: 'var(--color-bg, #ffffff)',
  page: 'var(--color-background-body, #f2f4f7)',
  fill: 'var(--color-fill-1, #f6f8f9)',
  fill2: 'var(--color-fill-2, #f4f5f8)',
  hover: 'var(--color-bg-hover, #f2f4f7)',
  text1: 'var(--color-text-1, #1e252e)',
  text2: 'var(--color-text-2, #475468)',
  text3: 'var(--color-text-3, #7588a3)',
  text4: 'var(--color-text-4, #b2bdcc)',
  primary: 'var(--color-primary, #155aef)',
  primaryBg: 'var(--color-primary-bg-active, #e1edfc)',
  success: 'var(--color-success, #27c274)',
  fail: 'var(--color-fail, #f43b2c)',
  warning: 'var(--color-warning, var(--theme-color-status-warning, #faad14))',
  mono: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  ease: '160ms cubic-bezier(0.2, 0.8, 0.2, 1)',
} as const;

const focusRing: CSSProperties = {
  outline: `2px solid color-mix(in srgb, var(--color-primary, #155aef) 45%, transparent)`,
  outlineOffset: 2,
};

export type UnifiedCardKind = 'studio' | 'skill' | 'wiki' | 'memory' | 'tool' | 'provider';

/** 全站统一 B 卡（选型 Look B）：wash + 固定解剖，仅内容字段因模块而异。 */

export type UnifiedOpsCardFooter = 'entity' | 'provider' | 'memory' | 'none';

export interface UnifiedOpsCardProps {
  name: string;
  description: string;
  icon?: string;
  vendorIcon?: string;
  status?: 'online' | 'offline' | 'ready' | 'building' | 'enabled' | 'disabled';
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
}

const statusMap: Record<
  NonNullable<UnifiedOpsCardProps['status']>,
  { label: string; tone: 'ok' | 'warn' | 'mute' | 'run' }
> = {
  online: { label: 'Online', tone: 'ok' },
  offline: { label: 'Offline', tone: 'mute' },
  ready: { label: '就绪', tone: 'ok' },
  building: { label: '构建中', tone: 'run' },
  enabled: { label: '启用', tone: 'ok' },
  disabled: { label: '停用', tone: 'mute' },
};

function StatusPill({ tone, label }: { tone: 'ok' | 'warn' | 'mute' | 'run'; label: string }) {
  const color =
    tone === 'ok'
      ? afterSys.success
      : tone === 'warn'
        ? afterSys.warning
        : tone === 'run'
          ? afterSys.primary
          : afterSys.text4;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        height: 20,
        padding: '0 8px',
        borderRadius: 999,
        fontSize: 11,
        lineHeight: 1,
        color: afterSys.text2,
        background: afterSys.fill,
        flexShrink: 0,
      }}
    >
      <span aria-hidden style={{ width: 6, height: 6, borderRadius: 999, background: color }} />
      {label}
    </span>
  );
}

/** 选型 B — 全模块统一卡片 */
export function UnifiedOpsCard({
  name,
  description,
  icon,
  vendorIcon,
  status,
  updatedAt,
  meta = [],
  pinned,
  showPin = true,
  footer = 'entity',
  owner = 'admin',
  team = 'Default',
  footerRight,
  modelCount,
  enabled,
}: UnifiedOpsCardProps) {
  const { shellProps, hover } = useUnifiedCardShell(name);
  const teamLabel = formatTeamLabel(team);
  const st = status ? statusMap[status] : null;
  const showStatusRow = Boolean(st || updatedAt);

  return (
    <article {...shellProps}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 10,
          padding: '14px 14px 0',
        }}
      >
        <div style={{ display: 'flex', gap: 12, minWidth: 0, flex: 1 }}>
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: afterSys.radiusSm,
              background: afterSys.fill,
              display: 'grid',
              placeItems: 'center',
              flexShrink: 0,
            }}
          >
            {vendorIcon ? (
               
              <img
                src={`/app/models/${vendorIcon}.svg`}
                alt=""
                width={22}
                height={22}
                style={{ objectFit: 'contain' }}
                onError={(event) => {
                  event.currentTarget.style.display = 'none';
                }}
              />
            ) : icon ? (
              <Icon type={icon} className="text-xl" style={{ color: afterSys.primary }} />
            ) : null}
          </div>
          <div style={{ minWidth: 0, flex: 1, paddingTop: 1 }}>
            <Tooltip title={name}>
              <Text
                strong
                style={{
                  display: 'block',
                  fontSize: 14,
                  letterSpacing: '-0.01em',
                  color: afterSys.text1,
                  lineHeight: 1.4,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {name}
              </Text>
            </Tooltip>
            {showStatusRow ? (
              <div
                style={{
                  marginTop: 6,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  minWidth: 0,
                }}
              >
                {st ? <StatusPill tone={st.tone} label={st.label} /> : null}
                {updatedAt ? (
                  <span style={{ fontSize: 12, color: afterSys.text3 }}>{updatedAt}</span>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
        <CardPinMenu pinned={pinned} showPin={showPin} hover={hover} />
      </div>

      <div style={{ padding: '10px 14px 14px', display: 'flex', flexDirection: 'column', gap: 10, flex: 1 }}>
        <Paragraph
          style={{
            margin: 0,
            fontSize: 12,
            lineHeight: 1.5,
            height: 36,
            color: afterSys.text2,
          }}
          ellipsis={{ rows: 2 }}
        >
          {description}
        </Paragraph>

        {meta.length > 0 ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, minHeight: 20 }}>
            {meta.map((m) => (
              <MetaChip key={m} label={m} />
            ))}
          </div>
        ) : null}

        {footer === 'none' ? null : (
          <div
            style={{
              paddingTop: 10,
              borderTop: afterSys.divider,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              fontSize: 12,
              color: afterSys.text3,
            }}
          >
            {footer === 'provider' ? (
              <>
                <span style={{ color: afterSys.text4 }}>{modelCount ?? 0} 个模型</span>
                <span onClick={(e) => e.stopPropagation()}>
                  <Switch size="small" checked={enabled ?? false} aria-label={`${name} 启用`} />
                </span>
              </>
            ) : footer === 'memory' ? (
              <>
                <span />
                <span
                  style={{
                    color: afterSys.text4,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: '62%',
                    textAlign: 'right',
                  }}
                >
                  {footerRight ?? '--'}
                </span>
              </>
            ) : (
              <>
                <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  <span style={{ color: afterSys.text4 }}>Owner</span>
                  <span style={{ margin: '0 6px', color: afterSys.text4 }}>·</span>
                  <span style={{ color: afterSys.text2 }}>{owner}</span>
                </div>
                <Tooltip title={teamLabel.full}>
                  <div
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      minWidth: 0,
                      maxWidth: '62%',
                      justifyContent: 'flex-end',
                    }}
                  >
                    <span style={{ color: afterSys.text4, flexShrink: 0 }}>Team</span>
                    <span style={{ color: afterSys.text4, flexShrink: 0 }}>·</span>
                    <span
                      style={{
                        color: afterSys.text2,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {teamLabel.primary}
                    </span>
                    {teamLabel.extra > 0 ? (
                      <span
                        style={{
                          flexShrink: 0,
                          height: 18,
                          padding: '0 6px',
                          borderRadius: 999,
                          fontSize: 11,
                          lineHeight: '18px',
                          fontVariantNumeric: 'tabular-nums',
                          color: afterSys.primary,
                          background: afterSys.primaryBg,
                        }}
                      >
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

/** @deprecated 使用 UnifiedOpsCard */
export type UnifiedEntityCardProps = UnifiedOpsCardProps;
/** @deprecated 使用 UnifiedOpsCard */
export type UnifiedMemoryCardProps = UnifiedOpsCardProps;
/** @deprecated 使用 UnifiedOpsCard */
export type UnifiedToolCardProps = UnifiedOpsCardProps;
/** @deprecated 使用 UnifiedOpsCard */
export type UnifiedProviderCardProps = UnifiedOpsCardProps;
export const UnifiedEntityCard = UnifiedOpsCard;
export const UnifiedMemoryCard = UnifiedOpsCard;
export const UnifiedToolCard = UnifiedOpsCard;
export const UnifiedProviderCard = UnifiedOpsCard;

const cardWash =
  'linear-gradient(180deg, color-mix(in srgb, var(--color-primary, #155aef) 4%, var(--color-bg, #fff)) 0%, var(--color-bg, #fff) 42%)';

const cardWashHover =
  'linear-gradient(180deg, color-mix(in srgb, var(--color-primary, #155aef) 6%, var(--color-bg-hover, #f2f4f7)) 0%, var(--color-bg-hover, #f2f4f7) 48%)';

function metaTagBg(hue: string) {
  return `color-mix(in srgb, ${hue} 13%, var(--color-bg, #fff))`;
}

const metaTagNeutral = {
  color: afterSys.text3,
  background: afterSys.fill,
} as const;

const metaTagTones = {
  primary: {
    color: 'var(--color-primary, #155aef)',
    background: metaTagBg('var(--color-primary, #155aef)'),
  },
  success: {
    color: 'var(--color-success, #27c274)',
    background: metaTagBg('var(--color-success, #27c274)'),
  },
  warning: {
    color: 'var(--theme-color-status-warning, #faad14)',
    background: metaTagBg('var(--theme-color-status-warning, #faad14)'),
  },
} as const;

function isNeutralMetaTag(label: string) {
  const key = label.trim().toLowerCase();
  if (/记忆条数/.test(label)) return true;
  if (/^v?\d/.test(key) || /\d+\s*(docs|models|条)/.test(key)) return true;
  if (/^(gpt-|deepseek|openai|anthropic|claude)/.test(key)) return true;
  if (key.includes('model')) return true;
  return false;
}

const metaTagSemanticTone: Record<string, keyof typeof metaTagTones> = {
  pilot: 'primary',
  chatflow: 'primary',
  lobechat: 'primary',
  rag: 'primary',
  'q&a': 'primary',
  planner: 'primary',
  mcp: 'primary',
  api: 'primary',
  团队: 'primary',
  个人: 'primary',
  ready: 'success',
  active: 'success',
  enabled: 'success',
  building: 'warning',
  openai: 'primary',
  其他: 'primary',
};

export function resolveMetaTagTone(label: string) {
  const key = label.trim().toLowerCase();
  if (isNeutralMetaTag(label)) return metaTagNeutral;
  const toneKey = metaTagSemanticTone[key];
  if (toneKey) return metaTagTones[toneKey];
  return metaTagNeutral;
}

function MetaChip({ label }: { label: string }) {
  const tone = resolveMetaTagTone(label);
  const accented = tone !== metaTagNeutral;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        height: 20,
        padding: '0 7px',
        borderRadius: afterSys.radiusSm,
        fontSize: 11,
        fontWeight: accented ? 500 : 400,
        color: tone.color,
        background: tone.background,
      }}
    >
      {label}
    </span>
  );
}

function useUnifiedCardShell(name: string) {
  const [hover, setHover] = useState(false);
  const [focus, setFocus] = useState(false);
  const shellProps = {
    tabIndex: 0 as const,
    role: 'button' as const,
    'aria-label': name,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    onFocus: () => setFocus(true),
    onBlur: () => setFocus(false),
    style: {
      background: hover ? cardWashHover : cardWash,
      border: afterSys.border,
      borderRadius: afterSys.radius,
      overflow: 'hidden' as const,
      cursor: 'pointer' as const,
      height: 'auto' as const,
      display: 'flex' as const,
      flexDirection: 'column' as const,
      transition: `background ${afterSys.ease}, border-color ${afterSys.ease}`,
      borderColor: hover || focus
        ? 'var(--color-border-2, #e6e9ee)'
        : 'var(--color-border-1, #edeff3)',
      ...(focus ? focusRing : null),
    },
  };
  return { shellProps, hover };
}

function formatTeamLabel(team: string | string[]): {
  primary: string;
  extra: number;
  full: string;
} {
  const list = (Array.isArray(team) ? team : [team]).map((t) => t.trim()).filter(Boolean);
  if (list.length === 0) return { primary: '--', extra: 0, full: '--' };
  return {
    primary: list[0],
    extra: Math.max(0, list.length - 1),
    full: list.join(','),
  };
}

function CardPinMenu({
  pinned,
  showPin = true,
  hover,
}: {
  pinned?: boolean;
  showPin?: boolean;
  hover: boolean;
}) {
  return (
    <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
      {showPin && pinned != null ? (
        <Tooltip title={pinned ? '取消置顶' : '置顶'}>
          <button
            type="button"
            aria-label={pinned ? '取消置顶' : '置顶'}
            onClick={(e) => e.stopPropagation()}
            style={{
              width: 28,
              height: 28,
              border: 'none',
              borderRadius: afterSys.radiusSm,
              background: 'transparent',
              color: pinned ? afterSys.primary : afterSys.text4,
              cursor: 'pointer',
              display: 'grid',
              placeItems: 'center',
            }}
          >
            {pinned ? <PushpinFilled style={{ fontSize: 12 }} /> : <PushpinOutlined style={{ fontSize: 12 }} />}
          </button>
        </Tooltip>
      ) : null}
      <Dropdown
        menu={{
          items: [
            { key: 'edit', label: '编辑' },
            { key: 'delete', label: '删除', danger: true },
          ],
        }}
        trigger={['click']}
      >
        <button
          type="button"
          aria-label="更多操作"
          onClick={(e) => e.stopPropagation()}
          style={{
            width: 28,
            height: 28,
            border: 'none',
            borderRadius: afterSys.radiusSm,
            background: hover ? afterSys.fill : 'transparent',
            color: afterSys.text3,
            cursor: 'pointer',
            display: 'grid',
            placeItems: 'center',
          }}
        >
          <MoreOutlined />
        </button>
      </Dropdown>
    </div>
  );
}

export function UnifiedFilterChips({
  options,
  value,
  onChange,
}: {
  options: { key: string; label: string; count?: number }[];
  value: string;
  onChange: (key: string) => void;
}) {
  return (
    <div role="tablist" aria-label="筛选" style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {options.map((o) => {
        const active = o.key === value;
        return (
          <button
            key={o.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.key)}
            style={{
              appearance: 'none',
              cursor: 'pointer',
              borderRadius: 999,
              padding: '4px 10px',
              fontSize: 12,
              lineHeight: 1.25,
              border: active
                ? '1px solid color-mix(in srgb, var(--color-primary, #155aef) 35%, var(--color-border-1, #edeff3))'
                : '1px solid transparent',
              background: active ? afterSys.primaryBg : 'transparent',
              color: active ? afterSys.primary : afterSys.text2,
              transition: `background ${afterSys.ease}, border-color ${afterSys.ease}, color ${afterSys.ease}`,
            }}
          >
            {o.label}
            {o.count != null ? (
              <span
                style={{
                  marginLeft: 6,
                  fontVariantNumeric: 'tabular-nums',
                  fontFamily: afterSys.mono,
                  fontSize: 11,
                  color: active ? afterSys.primary : afterSys.text4,
                }}
              >
                {o.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function UnifiedListChrome({
  title,
  subtitle,
  filters,
  filterValue,
  onFilterChange,
  searchPlaceholder,
  primaryAction = '新建',
  children,
  totalLabel,
}: {
  title: string;
  subtitle?: string;
  filters: { key: string; label: string; count?: number }[];
  filterValue: string;
  onFilterChange: (key: string) => void;
  searchPlaceholder: string;
  primaryAction?: string;
  children: ReactNode;
  totalLabel?: string;
}) {
  const [view, setView] = useState<'grid' | 'list'>('grid');

  return (
    <div style={{ display: 'grid', gap: afterSys.gap }}>
      <header
        style={{
          background: afterSys.bg,
          border: afterSys.border,
          borderRadius: afterSys.radius,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            padding: '14px 16px',
            display: 'flex',
            justifyContent: 'space-between',
            gap: 12,
            alignItems: 'flex-start',
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
              <h2
                style={{
                  margin: 0,
                  fontSize: 14,
                  fontWeight: 600,
                  letterSpacing: '-0.01em',
                  color: afterSys.text1,
                  lineHeight: 1.5,
                }}
              >
                {title}
              </h2>
              {totalLabel ? (
                <span style={{ fontSize: 12, color: afterSys.text4, fontVariantNumeric: 'tabular-nums' }}>
                  {totalLabel}
                </span>
              ) : null}
            </div>
            {subtitle ? (
              <p style={{ margin: '4px 0 0', fontSize: 12, color: afterSys.text3, lineHeight: 1.5 }}>{subtitle}</p>
            ) : null}
          </div>
          <Space size={8}>
            <Segmented
              size="small"
              value={view}
              onChange={(v) => setView(v as 'grid' | 'list')}
              options={[
                { value: 'grid', icon: <AppstoreOutlined />, title: '网格' },
                { value: 'list', icon: <UnorderedListOutlined />, title: '列表' },
              ]}
            />
            {primaryAction ? (
              <Button icon={<PlusOutlined />} type="primary" size="middle">
                {primaryAction}
              </Button>
            ) : null}
          </Space>
        </div>

        <div
          style={{
            padding: '10px 16px',
            display: 'flex',
            flexWrap: 'wrap',
            gap: 10,
            alignItems: 'center',
            justifyContent: 'space-between',
            background: afterSys.fill,
            borderTop: afterSys.divider,
          }}
        >
          <UnifiedFilterChips options={filters} value={filterValue} onChange={onFilterChange} />
          <Input.Search allowClear placeholder={searchPlaceholder} style={{ width: 248 }} size="middle" />
        </div>
      </header>

      <div
        style={
          view === 'grid'
            ? {
              display: 'grid',
              gridTemplateColumns: `repeat(auto-fill, minmax(${afterSys.cardMin}px, 1fr))`,
              gap: afterSys.gap,
            }
            : { display: 'grid', gap: 8 }
        }
      >
        {children}
      </div>
    </div>
  );
}

/** 分区卡与列表 Look B 同一材质：主色 wash、8px 圆角、细分割，不用灰底标题条。 */
export const afterPanel = {
  card: 'overflow-hidden rounded-[8px] border border-[var(--color-border-1)] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--color-primary,#155aef)_4%,var(--color-bg,#fff))_0%,var(--color-bg,#fff)_42%)]',
  head: 'flex min-h-10 shrink-0 items-center border-b border-[var(--color-fill-2)] px-3.5 py-2 text-[14px] font-semibold tracking-tight text-[var(--color-text-1)]',
} as const;

export function AfterSectionCard({
  title,
  extra,
  children,
  className = '',
}: {
  title: ReactNode;
  extra?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`${afterPanel.card} ${className}`}>
      <div className={`${afterPanel.head} ${extra ? 'justify-between gap-2' : ''}`}>
        <div className="min-w-0 flex-1">{title}</div>
        {extra ? <div className="flex shrink-0 items-center">{extra}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function PageEffectFrame({
  route,
  title,
  refs,
  children,
}: {
  route: string;
  title: string;
  refs: string[];
  children: ReactNode;
}) {
  return (
    <div
      style={{
        background: afterSys.page,
        color: afterSys.text1,
        minHeight: 520,
        padding: afterSys.pagePad,
      }}
    >
      <div
        style={{
          marginBottom: 14,
          display: 'flex',
          justifyContent: 'space-between',
          gap: 12,
          alignItems: 'flex-end',
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div style={{ fontSize: 11, color: afterSys.text4, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
            After · OpsPilot · token
          </div>
          <div style={{ marginTop: 2, fontSize: 16, fontWeight: 600, letterSpacing: '-0.02em', color: afterSys.text1, lineHeight: 1.5 }}>
            {title}
          </div>
          <code style={{ fontSize: 11, color: afterSys.text4, fontFamily: afterSys.mono }}>{route}</code>
        </div>
        <div style={{ fontSize: 11, color: afterSys.text4, maxWidth: 420, textAlign: 'right', lineHeight: 1.45 }}>
          参考 {refs.join(' · ')} · 工具栏可切明暗
        </div>
      </div>
      {children}
    </div>
  );
}

export function BeautifulInsightStrip({
  items,
}: {
  items: { label: string; value: string; hint?: string; delta?: string; tone?: 'ok' | 'warn' | 'mute' }[];
}) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.min(items.length, 4)}, minmax(0, 1fr))`,
        gap: 12,
      }}
    >
      {items.map((it) => (
        <div
          key={it.label}
          style={{
            background: afterSys.bg,
            border: afterSys.border,
            borderRadius: afterSys.radius,
            padding: '12px 14px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: afterSys.text3 }}>{it.label}</span>
            {it.delta ? (
              <span
                style={{
                  fontSize: 11,
                  fontVariantNumeric: 'tabular-nums',
                  color: it.tone === 'warn' ? afterSys.warning : afterSys.success,
                }}
              >
                {it.delta}
              </span>
            ) : null}
          </div>
          <div
            style={{
              marginTop: 6,
              fontSize: 22,
              fontWeight: 600,
              fontVariantNumeric: 'tabular-nums',
              letterSpacing: '-0.03em',
              color: afterSys.text1,
              lineHeight: 1.1,
            }}
          >
            {it.value}
          </div>
          {it.hint ? (
            <div style={{ marginTop: 6, fontSize: 11, color: afterSys.text4 }}>{it.hint}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function CompactConfidenceBar({ percent }: { percent: number }) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: afterSys.text3 }}>
        <span>置信度</span>
        <span style={{ fontVariantNumeric: 'tabular-nums', fontFamily: afterSys.mono }}>{percent}%</span>
      </div>
      <Progress
        percent={percent}
        showInfo={false}
        size="small"
        strokeColor={afterSys.primary}
        trailColor={afterSys.fill2}
        style={{ marginTop: 4, marginBottom: 0 }}
      />
    </div>
  );
}

export function useListFilter(defaultKey = 'all') {
  const [filter, setFilter] = useState(defaultKey);
  return { filter, setFilter };
}

export function SegmentedPanel({
  options,
  children,
}: {
  options: string[];
  children: (active: string) => ReactNode;
}) {
  const [active, setActive] = useState(options[0]);
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <Segmented options={options} value={active} onChange={(v) => setActive(String(v))} />
      {children(active)}
    </div>
  );
}

/** Quiet surface — same border language as cards; meta strip uses fill without second border weight */
export function Surface({
  children,
  meta,
  padded = true,
}: {
  children: ReactNode;
  meta?: ReactNode;
  padded?: boolean;
}) {
  return (
    <div
      style={{
        border: afterSys.border,
        borderRadius: afterSys.radius,
        background: afterSys.bg,
        overflow: 'hidden',
      }}
    >
      {meta ? (
        <div
          style={{
            padding: '6px 10px',
            borderBottom: afterSys.divider,
            background: afterSys.fill,
            display: 'flex',
            justifyContent: 'space-between',
            gap: 8,
            alignItems: 'center',
            fontSize: 11,
            color: afterSys.text4,
            fontFamily: afterSys.mono,
          }}
        >
          {meta}
        </div>
      ) : null}
      <div style={{ padding: padded ? 10 : 0 }}>{children}</div>
    </div>
  );
}
