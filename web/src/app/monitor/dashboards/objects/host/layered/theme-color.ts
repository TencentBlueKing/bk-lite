'use client';

import { useEffect, useState } from 'react';

const THEME_COLOR_TOKENS = [
  '--color-bg',
  '--color-border',
  '--color-text-1',
  '--color-text-3',
  '--color-success',
  '--color-warning',
  '--color-fail'
] as const;

const CSS_VAR_RE = /^var\((--[a-z0-9-]+)\)/i;

const readTokens = () => {
  if (typeof window === 'undefined') return {} as Record<string, string>;
  const style = getComputedStyle(document.documentElement);
  const next: Record<string, string> = {};
  THEME_COLOR_TOKENS.forEach((token) => {
    next[token] = style.getPropertyValue(token).trim();
  });
  return next;
};

export const readThemeColor = (token: string) => {
  if (typeof window === 'undefined') return '';
  return getComputedStyle(document.documentElement).getPropertyValue(token).trim();
};

export const resolveThemeColor = (value: string | undefined, computed: Record<string, string>) => {
  if (!value) return '';
  const match = CSS_VAR_RE.exec(value.trim());
  if (!match) return value;
  return computed[match[1]] || readThemeColor(match[1]);
};

export const useThemeColors = () => {
  const [colors, setColors] = useState<Record<string, string>>(readTokens);
  useEffect(() => {
    const read = () => setColors(readTokens());
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style'] });
    return () => observer.disconnect();
  }, []);
  return colors;
};
