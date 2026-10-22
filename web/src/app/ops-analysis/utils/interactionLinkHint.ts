import {
  shouldNavigateInteraction,
  type InteractionSurface,
} from '@/app/ops-analysis/utils/interactionLink';

export type DataLinkHintTheme = 'light' | 'dark';

type HintLink = { kind?: string } | null | undefined;

export const shouldShowDataLinkHint = (
  surface: InteractionSurface,
  link: HintLink,
) => shouldNavigateInteraction(surface) && link?.kind === 'data';

export const resolveDataLinkTooltipTheme = (
  chartThemeMode: string | undefined,
  appTheme: 'light' | 'dark' = 'light',
): DataLinkHintTheme => {
  if (chartThemeMode === 'screen-dark') return 'dark';
  if (chartThemeMode === 'screen-light') return 'light';
  return appTheme === 'dark' ? 'dark' : 'light';
};

export const escapeInteractionTooltipHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

export const dataLinkTooltipFooterStyle = (theme: DataLinkHintTheme = 'light') => {
  const palette = theme === 'dark'
    ? { color: 'rgba(232, 238, 247, 0.62)', border: 'rgba(255, 255, 255, 0.18)' }
    : { color: 'rgba(30, 37, 46, 0.55)', border: 'rgba(30, 37, 46, 0.12)' };
  return {
    marginTop: '0.45em',
    paddingTop: '0.35em',
    borderTop: `1px solid ${palette.border}`,
    fontSize: '0.85em',
    lineHeight: '1.35',
    fontWeight: '400',
    color: palette.color,
  };
};

export const dataLinkTooltipFooterHtml = (
  text: string,
  theme: DataLinkHintTheme = 'light',
) => {
  const style = Object.entries(dataLinkTooltipFooterStyle(theme))
    .map(([key, value]) => `${key.replace(/[A-Z]/g, (char) => `-${char.toLowerCase()}`)}:${value}`)
    .join(';');
  return `<div data-ops-link-hint="true" style="${style}">${escapeInteractionTooltipHtml(text)}</div>`;
};

export const appendDataLinkTooltipFooter = (
  html: unknown,
  footerText: string,
  theme: DataLinkHintTheme = 'light',
) => {
  if (typeof html !== 'string' || !html.trim() || !footerText.trim()) return html;
  const footer = dataLinkTooltipFooterHtml(footerText, theme);
  const trimmed = html.trimEnd();
  if (trimmed.endsWith('</div>')) {
    return `${trimmed.slice(0, -'</div>'.length)}${footer}</div>`;
  }
  return `${html}${footer}`;
};

export interface DataLinkTooltipHintOptions {
  surface: InteractionSurface;
  link: HintLink;
  footerText: string;
  theme?: DataLinkHintTheme;
  fallback?: (...args: any[]) => unknown;
  /** 与点击共用：这一列不能跳时不追加提示。 */
  includeFooter?: (...args: any[]) => boolean;
}

export const wrapDataLinkTooltipFormatter = <T extends (...args: any[]) => unknown>(
  formatter: T | undefined,
  options: DataLinkTooltipHintOptions,
): T | undefined => {
  if (!shouldShowDataLinkHint(options.surface, options.link) || !options.footerText.trim()) {
    return formatter;
  }
  const wrapped = (...args: Parameters<T>) => {
    const raw = formatter ? formatter(...args) : options.fallback?.(...args);
    if (options.includeFooter && !options.includeFooter(...args)) return raw;
    return appendDataLinkTooltipFooter(raw, options.footerText, options.theme);
  };
  return wrapped as T;
};
