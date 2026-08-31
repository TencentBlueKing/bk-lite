import { CARD_TONE } from './application3DCardStyle';
import {
  neonLevelToCardTone,
  resolveApplication3DCardVisual,
  type Application3DCardTone,
  type Application3DTranslate,
} from './application3DLayout';
import { resolveNeonLevel } from './application3DVisual';

/** Reuse Wall card status accents; Detail only dials intensity via CSS usage. */
export const DETAIL_STATUS_ACCENT = {
  normal: {
    border: 'rgba(206, 220, 232, 0.28)',
    glow: 'rgba(0, 0, 0, 0)',
    glowWidth: 0,
    softGlow: 'rgba(0, 0, 0, 0)',
    edgeWidth: 1.5,
    dot: CARD_TONE.normal.dot,
    badgeBg: 'rgba(28, 44, 58, 0.42)',
    badgeBorder: 'rgba(160, 184, 210, 0.42)',
    badgeText: 'rgba(198, 222, 218, 0.92)',
  },
  critical: {
    border: 'rgba(255, 92, 84, 0.92)',
    glow: 'rgba(255, 70, 58, 0.42)',
    glowWidth: 22,
    softGlow: 'rgba(220, 40, 36, 0.22)',
    edgeWidth: 1.5,
    dot: '#ff7a72',
    badgeBg: 'rgba(120, 28, 24, 0.35)',
    badgeBorder: 'var(--color-application3d-severity-badge-critical-border)',
    badgeText: 'var(--color-application3d-severity-critical)',
  },
  error: {
    border: 'rgba(232, 140, 60, 0.9)',
    glow: 'rgba(232, 124, 40, 0.32)',
    glowWidth: 18,
    softGlow: 'rgba(200, 96, 24, 0.18)',
    edgeWidth: 1.5,
    dot: '#f0a060',
    badgeBg: 'rgba(100, 48, 12, 0.35)',
    badgeBorder: 'var(--color-application3d-severity-badge-error-border)',
    badgeText: 'var(--color-application3d-severity-error)',
  },
  warning: {
    border: 'rgba(236, 176, 80, 0.88)',
    glow: 'rgba(230, 160, 56, 0.28)',
    glowWidth: 16,
    softGlow: 'rgba(196, 128, 36, 0.16)',
    edgeWidth: 1.5,
    dot: '#f0c070',
    badgeBg: 'rgba(96, 60, 12, 0.35)',
    badgeBorder: 'var(--color-application3d-severity-badge-warning-border)',
    badgeText: 'var(--color-application3d-severity-warning)',
  },
  info: {
    border: 'rgba(96, 176, 250, 0.72)',
    glow: 'rgba(80, 160, 240, 0.18)',
    glowWidth: 12,
    softGlow: 'rgba(56, 120, 200, 0.1)',
    edgeWidth: 1.5,
    dot: '#7ec0ff',
    badgeBg: 'rgba(24, 56, 96, 0.35)',
    badgeBorder: 'var(--color-application3d-severity-badge-info-border)',
    badgeText: 'var(--color-application3d-severity-info)',
  },
  unknown: {
    border: 'rgba(130, 142, 156, 0.55)',
    glow: 'rgba(0, 0, 0, 0)',
    glowWidth: 0,
    softGlow: 'rgba(0, 0, 0, 0)',
    edgeWidth: 1.5,
    dot: CARD_TONE.unknown.dot,
    badgeBg: 'rgba(40, 50, 64, 0.45)',
    badgeBorder: 'rgba(140, 156, 176, 0.55)',
    badgeText: 'rgba(198, 208, 220, 0.92)',
  },
} as const satisfies Record<
  Application3DCardTone,
  {
    border: string;
    glow: string;
    glowWidth: number;
    softGlow: string;
    edgeWidth: number;
    dot: string;
    badgeBg: string;
    badgeBorder: string;
    badgeText: string;
  }
>;

export const SEVERITY_DOT: Record<'critical' | 'error' | 'warning' | 'info', string> = {
  critical: 'var(--color-application3d-severity-critical)',
  error: 'var(--color-application3d-severity-error)',
  warning: 'var(--color-application3d-severity-warning)',
  info: 'var(--color-application3d-severity-info)',
};

export const SEVERITY_BADGE: Record<
  'critical' | 'error' | 'warning' | 'info',
  { border: string; color: string; bg: string }
> = {
  critical: {
    border: 'var(--color-application3d-severity-badge-critical-border)',
    color: 'var(--color-application3d-severity-critical)',
    bg: 'rgba(120, 28, 24, 0.35)',
  },
  error: {
    border: 'var(--color-application3d-severity-badge-error-border)',
    color: 'var(--color-application3d-severity-error)',
    bg: 'rgba(100, 48, 12, 0.35)',
  },
  warning: {
    border: 'var(--color-application3d-severity-badge-warning-border)',
    color: 'var(--color-application3d-severity-warning)',
    bg: 'rgba(96, 60, 12, 0.35)',
  },
  info: {
    border: 'var(--color-application3d-severity-badge-info-border)',
    color: 'var(--color-application3d-severity-info)',
    bg: 'rgba(24, 56, 96, 0.35)',
  },
};

const BASIC_KEYS = new Set(['app_id', 'app_type', 'organization']);
const MAINTAIN_KEYS = new Set(['operator', 'bak_operator']);
const DESCRIPTION_KEYS = new Set(['comment']);

export interface DetailProperty { key: string; label: string; displayValue: string }

export interface DetailPropertySections {
  basic: DetailProperty[];
  maintain: DetailProperty[];
  description: DetailProperty[];
  other: DetailProperty[];
}

export const groupDetailProperties = (properties: DetailProperty[]): DetailPropertySections => {
  const sections: DetailPropertySections = {
    basic: [],
    maintain: [],
    description: [],
    other: [],
  };
  properties.forEach((property) => {
    if (BASIC_KEYS.has(property.key)) sections.basic.push(property);
    else if (MAINTAIN_KEYS.has(property.key)) sections.maintain.push(property);
    else if (DESCRIPTION_KEYS.has(property.key)) sections.description.push(property);
    else sections.other.push(property);
  });
  return sections;
};

export const resolveDetailStatus = (
  item: {
    name: string;
    health: {
      state: string;
      reason: string;
      activeAlarmCount: number | null;
      highestSeverity: { id: string; label: string; color: string } | null;
    };
  },
  t: Application3DTranslate,
) => {
  const visual = resolveApplication3DCardVisual(item, t);
  const tone = neonLevelToCardTone(resolveNeonLevel(item));
  const accent = DETAIL_STATUS_ACCENT[tone];
  return {
    tone,
    statusLabel: visual.statusLabel,
    accent,
    leftPanelStyle: {
      border: `${accent.edgeWidth}px solid ${accent.border}`,
      boxShadow:
        accent.glowWidth > 0
          ? [
              `0 0 0 1px ${accent.border}`,
              `0 0 ${Math.round(accent.glowWidth * 0.55)}px ${accent.glow}`,
              `0 0 ${accent.glowWidth + 10}px ${accent.softGlow}`,
              'var(--color-application3d-detail-glass-highlight)',
              'var(--color-application3d-detail-glass-shadow)',
          ].join(', ')
          : '0 0 0 1px rgba(160, 180, 204, 0.12), var(--color-application3d-detail-glass-highlight), var(--color-application3d-detail-glass-shadow)',
    } as const,
  };
};

export const formatAlarmDurationSeconds = (seconds: number): string => {
  const safe = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  const days = Math.floor(safe / 86400);
  const hours = Math.floor((safe % 86400) / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
};

export const formatAlarmOccurredAt = (iso: string | null | undefined): string => {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '-';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

export const formatTrendAxisTime = (isoOrMs: string | number): string => {
  const date = typeof isoOrMs === 'number' ? new Date(isoOrMs) : new Date(isoOrMs);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
};

/** Nice Y ticks spanning data + thresholds. */
export const buildTrendYTicks = (min: number, max: number, count = 5): number[] => {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0];
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1;
    return [min - pad, min, min + pad];
  }
  const span = max - min;
  const step = span / Math.max(count - 1, 1);
  const rough = 10 ** Math.floor(Math.log10(step || 1));
  const niceStep = [1, 2, 2.5, 5, 10]
    .map((m) => m * rough)
    .find((candidate) => candidate >= step) || step;
  const niceMin = Math.floor(min / niceStep) * niceStep;
  const niceMax = Math.ceil(max / niceStep) * niceStep;
  const ticks: number[] = [];
  for (let value = niceMin; value <= niceMax + niceStep / 2; value += niceStep) {
    ticks.push(Number(value.toFixed(6)));
  }
  return ticks.length ? ticks : [min, max];
};

export const projectTrendX = (
  timestampMs: number,
  domainMin: number,
  domainMax: number,
  plotLeft: number,
  plotWidth: number,
): number => {
  const span = Math.max(domainMax - domainMin, 1);
  return plotLeft + ((timestampMs - domainMin) / span) * plotWidth;
};

export const projectTrendY = (
  value: number,
  domainMin: number,
  domainMax: number,
  plotTop: number,
  plotHeight: number,
): number => {
  const span = Math.max(domainMax - domainMin, 1);
  return plotTop + plotHeight - ((value - domainMin) / span) * plotHeight;
};
