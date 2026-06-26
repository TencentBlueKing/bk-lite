const DEFAULT_GLOW_COLOR = 'rgba(56, 189, 248, 0.36)';

export const toRgbaColor = (
  color: string | undefined,
  alpha: number,
  fallback = DEFAULT_GLOW_COLOR,
): string => {
  if (!color) return fallback;

  const normalized = color.trim();
  if (
    !normalized ||
    normalized === 'transparent' ||
    normalized === 'none' ||
    normalized === 'rgba(0,0,0,0)'
  ) {
    return fallback;
  }

  const rgbMatch = normalized.match(/^rgba?\(([^)]+)\)$/i);
  if (rgbMatch) {
    const [r, g, b] = rgbMatch[1]
      .split(',')
      .slice(0, 3)
      .map((part) => Number(part.trim()));
    if ([r, g, b].every((value) => Number.isFinite(value))) {
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }
  }

  const hexMatch = normalized.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hexMatch) {
    const hex = hexMatch[1].length === 3
      ? hexMatch[1].split('').map((char) => `${char}${char}`).join('')
      : hexMatch[1];
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  return fallback;
};

export const getNodeGlowAttrs = (
  borderColor: string | undefined,
  strokeWidth = 1,
): Record<string, any> => {
  const softGlow = toRgbaColor(borderColor, 0.24);

  return {
    stroke: borderColor || DEFAULT_GLOW_COLOR,
    strokeWidth: Math.max(Number(strokeWidth) || 0, 1),
    filter: `drop-shadow(0 0 6px ${softGlow})`,
  };
};

export const buildTechFramePath = (
  width: number,
  height: number,
  options: { inset?: number; cornerSize?: number } = {},
): string => {
  const inset = Math.max(0, Number(options.inset) || 0);
  const availableWidth = Math.max(0, width - inset * 2);
  const availableHeight = Math.max(0, height - inset * 2);
  const maxCorner = Math.max(0, Math.min(availableWidth, availableHeight) / 2);
  const corner = Math.min(Math.max(0, Number(options.cornerSize) || 0), maxCorner);

  const left = inset;
  const top = inset;
  const right = width - inset;
  const bottom = height - inset;

  return [
    `M${left + corner} ${top}`,
    `H${right - corner}`,
    `L${right} ${top + corner}`,
    `V${bottom - corner}`,
    `L${right - corner} ${bottom}`,
    `H${left + corner}`,
    `L${left} ${bottom - corner}`,
    `V${top + corner}`,
    'Z',
  ].join(' ');
};

export const resolveConfiguredNodeSize = (
  styleConfig: { width?: number; height?: number } | undefined,
  fallback: { width: number; height: number },
): { width: number; height: number } => ({
  width: Number(styleConfig?.width) || fallback.width,
  height: Number(styleConfig?.height) || fallback.height,
});
