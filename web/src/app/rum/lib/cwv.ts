/** Core Web Vitals thresholds and experience health. */

export type CwvMetric = 'lcp' | 'inp' | 'cls' | 'fcp' | 'ttfb' | 'fid';

/** [good upper, needs-improvement upper]. */
export const CWV_THRESHOLDS: Record<CwvMetric, [number, number]> = {
  lcp: [2500, 4000],
  inp: [200, 500],
  cls: [0.1, 0.25],
  fcp: [1800, 3000],
  ttfb: [800, 1800],
  fid: [100, 300],
};

export type CwvTone = 'success' | 'warning' | 'danger' | 'neutral';

export function cwvTone(name: string, v: number): CwvTone {
  if (v <= 0) return 'neutral';
  const bounds = CWV_THRESHOLDS[name as CwvMetric];
  if (!bounds) return 'neutral';
  const [good, poor] = bounds;
  if (v <= good) return 'success';
  if (v <= poor) return 'warning';
  return 'danger';
}

/** App-level experience health from LCP/INP P75 + error rate (0–1). */
export function appExperienceTone(lcpP75: number, inpP75: number, errorRate: number): CwvTone {
  const cwv = [cwvTone('lcp', lcpP75), cwvTone('inp', inpP75)];
  const errPct = errorRate * 100;
  if (errPct > 5 || cwv.includes('danger')) return 'danger';
  if (errPct > 0 || cwv.includes('warning')) return 'warning';
  if (cwv.includes('success')) return 'success';
  return 'neutral';
}

export function errorRateTone(rate: number): CwvTone {
  if (rate > 0.05) return 'danger';
  if (rate > 0) return 'warning';
  return 'success';
}

export function formatPct(rate: number): string {
  const unit = Number.isFinite(rate) ? Math.min(1, Math.max(0, rate)) : 0;
  return `${(unit * 100).toFixed(2)}%`;
}

export function formatMs(v: number): string {
  return v > 0 ? `${Math.round(v)}ms` : '—';
}

/** Status dots — semantic tokens only (DESIGN Token First). */
export function toneDotClass(tone: CwvTone): string {
  switch (tone) {
    case 'success':
      return 'bg-[var(--color-success)]';
    case 'warning':
      return 'bg-[var(--theme-color-status-warning)]';
    case 'danger':
      return 'bg-[var(--color-fail)]';
    default:
      return 'bg-[var(--color-text-4)]';
  }
}

export function toneTextClass(tone: CwvTone): string {
  switch (tone) {
    case 'success':
      return 'text-[var(--color-success)]';
    case 'warning':
      return 'text-[var(--theme-color-status-warning)]';
    case 'danger':
      return 'text-[var(--color-fail)]';
    default:
      return 'text-[var(--color-text-3)]';
  }
}

export function toneBarClass(tone: CwvTone): string {
  switch (tone) {
    case 'success':
      return 'bg-[var(--color-success)]';
    case 'warning':
      return 'bg-[var(--theme-color-status-warning)]';
    case 'danger':
      return 'bg-[var(--color-fail)]';
    default:
      return 'bg-[var(--color-text-4)]';
  }
}

export function toneSoftBgClass(tone: CwvTone): string {
  switch (tone) {
    case 'success':
      return 'bg-[color-mix(in_srgb,var(--color-success)_12%,var(--color-bg))] text-[var(--color-success)]';
    case 'warning':
      return 'bg-[color-mix(in_srgb,var(--theme-color-status-warning)_12%,var(--color-bg))] text-[var(--theme-color-status-warning)]';
    case 'danger':
      return 'bg-[color-mix(in_srgb,var(--color-fail)_12%,var(--color-bg))] text-[var(--color-fail)]';
    default:
      return 'bg-[var(--color-fill-2)] text-[var(--color-text-3)]';
  }
}

/** Palette for shared `SemanticBadge` (DESIGN: AntD → shared → app-local). */
export type RumBadgeTone = CwvTone | 'info';

export function toneSemanticPalette(tone: RumBadgeTone): {
  textColor: string;
  backgroundColor: string;
} {
  switch (tone) {
    case 'success':
      return {
        textColor: 'var(--color-success)',
        backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, var(--color-bg))',
      };
    case 'warning':
      return {
        textColor: 'var(--theme-color-status-warning)',
        backgroundColor: 'color-mix(in srgb, var(--theme-color-status-warning) 12%, var(--color-bg))',
      };
    case 'danger':
      return {
        textColor: 'var(--color-fail)',
        backgroundColor: 'color-mix(in srgb, var(--color-fail) 12%, var(--color-bg))',
      };
    case 'info':
      return {
        textColor: 'var(--color-primary)',
        backgroundColor: 'color-mix(in srgb, var(--color-primary) 12%, var(--color-bg))',
      };
    default:
      return {
        textColor: 'var(--color-text-3)',
        backgroundColor: 'var(--color-fill-2)',
      };
  }
}

export function toneColor(tone: CwvTone): string {
  switch (tone) {
    case 'success':
      return 'var(--color-success)';
    case 'warning':
      return 'var(--theme-color-status-warning)';
    case 'danger':
      return 'var(--color-fail)';
    default:
      return 'var(--color-text-3)';
  }
}

