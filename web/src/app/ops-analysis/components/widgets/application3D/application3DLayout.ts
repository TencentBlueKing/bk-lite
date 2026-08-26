export interface Application3DLayout {
  columns: number;
  rows: number;
  cardWidth: number;
  cardHeight: number;
  gapX: number;
  gapY: number;
  wallWidth: number;
  wallHeight: number;
}

export interface Application3DCardVisual {
  /** Short wall title (common demo prefix stripped when present). */
  title: string;
  /** Human-readable status line; not color-only. */
  statusLabel: string;
  /** Semantic accent used for border / badge / status dot. */
  accentTokenCandidates: string[];
  /** Badge fill uses accent; text must contrast (always light on saturated accent). */
  badgeTextTokenCandidates: string[];
  showBadge: boolean;
  badgeText: string;
}

const CARD_ASPECT = 1.75;

const DEMO_NAME_PREFIX = '本地演示-';

const SEVERITY_ACCENT: Record<
  string,
  { tokens: string[] }
> = {
  critical: {
    tokens: ['--color-fail', '--theme-color-status-error'],
  },
  danger: {
    tokens: ['--color-fail', '--theme-color-status-error'],
  },
  warning: {
    tokens: ['--theme-color-status-warning', '--color-warning'],
  },
  info: {
    tokens: ['--theme-color-status-info', '--color-primary'],
  },
  success: {
    tokens: ['--color-success', '--theme-color-status-success'],
  },
};

export const buildApplication3DLayout = (
  count: number,
  viewportAspect: number,
): Application3DLayout => {
  const safeCount = Math.max(0, Math.floor(count));
  const safeAspect = Math.max(viewportAspect, 0.1);
  const columns = safeCount
    ? Math.min(
      safeCount,
      Math.max(1, Math.ceil(Math.sqrt((safeCount * safeAspect) / CARD_ASPECT))),
    )
    : 1;
  const rows = Math.max(1, Math.ceil(safeCount / columns));
  const density = safeCount > 100 ? 0.72 : safeCount > 50 ? 0.82 : 1;
  const cardWidth = 3.5 * density;
  const cardHeight = cardWidth / CARD_ASPECT;
  const gapX = 0.45 * density;
  const gapY = 0.5 * density;
  return {
    columns,
    rows,
    cardWidth,
    cardHeight,
    gapX,
    gapY,
    wallWidth: columns * cardWidth + Math.max(0, columns - 1) * gapX,
    wallHeight: rows * cardHeight + Math.max(0, rows - 1) * gapY,
  };
};

export const formatApplicationAlarmBadge = (count: number | null): string => {
  if (count === null) return '?';
  if (count >= 100) return '99+';
  return String(Math.max(0, Math.floor(count)));
};

export const formatApplication3DCardTitle = (name: string): string => {
  const trimmed = name.trim();
  if (trimmed.startsWith(DEMO_NAME_PREFIX) && trimmed.length > DEMO_NAME_PREFIX.length) {
    return trimmed.slice(DEMO_NAME_PREFIX.length);
  }
  return trimmed;
};

/**
 * Resolve Wall card chrome from health DTO.
 * Uses highestSeverity / reason so alarming cards are not collapsed into one look.
 */
export const resolveApplication3DCardVisual = (item: {
  name: string;
  health: {
    state: string;
    reason: string;
    activeAlarmCount: number | null;
    highestSeverity: { id: string; label: string; color: string } | null;
  };
}): Application3DCardVisual => {
  const { health } = item;
  const badgeText = formatApplicationAlarmBadge(health.activeAlarmCount);
  const showBadge = badgeText !== '0';

  if (health.state === 'normal') {
    return {
      title: formatApplication3DCardTitle(item.name),
      statusLabel: 'NORMAL',
      accentTokenCandidates: SEVERITY_ACCENT.success.tokens,
      badgeTextTokenCandidates: ['--color-white', '--color-bg-1'],
      showBadge: false,
      badgeText: '0',
    };
  }

  if (health.reason === 'unavailable') {
    return {
      title: formatApplication3DCardTitle(item.name),
      statusLabel: 'UNAVAILABLE',
      accentTokenCandidates: ['--color-text-3', '--theme-color-text-tertiary'],
      badgeTextTokenCandidates: ['--color-white', '--color-bg-1'],
      showBadge: true,
      badgeText: '?',
    };
  }

  if (health.reason === 'no_data_alarm') {
    return {
      title: formatApplication3DCardTitle(item.name),
      statusLabel: 'NO DATA',
      accentTokenCandidates: SEVERITY_ACCENT.warning.tokens,
      badgeTextTokenCandidates: ['--color-text-1'],
      showBadge,
      badgeText,
    };
  }

  const severity = health.highestSeverity;
  const severityAccent =
    (severity && SEVERITY_ACCENT[severity.color]) ||
    (severity && SEVERITY_ACCENT[severity.id]) ||
    SEVERITY_ACCENT.danger;

  return {
    title: formatApplication3DCardTitle(item.name),
    statusLabel: (severity?.label || severity?.id || 'ALARM').toUpperCase(),
    accentTokenCandidates: severityAccent.tokens,
    badgeTextTokenCandidates: ['--color-white', '--color-bg-1'],
    showBadge,
    badgeText,
  };
};
