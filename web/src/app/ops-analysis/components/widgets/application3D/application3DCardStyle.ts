import type { Application3DCardTone, Application3DCardVisual } from './application3DLayout';

/**
 * Dark frosted glass for wall cards. Canvas cannot use CSS backdrop-filter,
 * so frost, rim light and translucency are painted. Faces use MeshBasicMaterial
 * so the painted glass is the on-screen truth; Physical lighting created a
 * metallic top-edge highlight at wall scale. Status is an edge accent, not a fill.
 */
export const CARD_THICKNESS = 0.2;

export type Application3DCardFace = 'front' | 'back';

export const CARD_GLASS = {
  radius: 32,
  inset: 4,
  bodyCenter: 'rgba(26, 36, 52, 0.62)',
  body: 'rgba(30, 42, 60, 0.48)',
  bodyRim: 'rgba(58, 78, 104, 0.28)',
  unknownBodyCenter: 'rgba(26, 30, 38, 0.64)',
  unknownBody: 'rgba(30, 34, 42, 0.50)',
  unknownBodyRim: 'rgba(54, 62, 76, 0.30)',
  innerShadow: 'rgba(0, 0, 0, 0.08)',
  title: 'rgba(248, 250, 252, 0.98)',
  titleUnknown: 'rgba(232, 236, 242, 0.96)',
  frostAlpha: 0.045,
  frostGain: 0.032,
  frostStep: 3,
  fontFamily: '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif',
  titleSize: 54,
  statusSize: 27,
} as const;

export const CARD_BADGE = {
  height: 46,
  radius: 6,
  fontSize: 26,
  inset: 20,
} as const;

export const CARD_TONE = {
  normal: {
    edge: 'rgba(206, 220, 232, 0.16)',
    edgeWidth: 2.8,
    glow: { color: 'rgba(0, 0, 0, 0)', width: 0 },
    innerGlow: 'rgba(0, 0, 0, 0)',
    dot: '#3cbcb0',
    statusText: 'rgba(198, 222, 218, 0.96)',
    badgeFill: 'rgba(176, 48, 44, 0.96)',
  },
  critical: {
    edge: 'rgba(246, 86, 76, 1)',
    edgeWidth: 5.8,
    glow: { color: 'rgba(224, 44, 36, 0.38)', width: 22 },
    innerGlow: 'rgba(255, 118, 108, 0.26)',
    dot: '#e05650',
    statusText: 'rgba(240, 198, 194, 0.96)',
    badgeFill: 'rgba(188, 48, 44, 0.96)',
  },
  warning: {
    edge: 'rgba(236, 168, 74, 0.90)',
    edgeWidth: 4.2,
    glow: { color: 'rgba(210, 132, 48, 0.20)', width: 14 },
    innerGlow: 'rgba(0, 0, 0, 0)',
    dot: '#d9a05c',
    statusText: 'rgba(230, 208, 176, 0.95)',
    badgeFill: 'rgba(196, 126, 40, 0.96)',
  },
  error: {
    edge: 'rgba(232, 124, 52, 0.96)',
    edgeWidth: 5.0,
    glow: { color: 'rgba(217, 112, 7, 0.28)', width: 18 },
    innerGlow: 'rgba(255, 160, 96, 0.18)',
    dot: '#d97007',
    statusText: 'rgba(240, 208, 176, 0.96)',
    badgeFill: 'rgba(184, 96, 24, 0.96)',
  },
  info: {
    edge: 'rgba(96, 165, 250, 0.62)',
    edgeWidth: 3.4,
    glow: { color: 'rgba(0, 0, 0, 0)', width: 0 },
    innerGlow: 'rgba(0, 0, 0, 0)',
    dot: '#60a5fa',
    statusText: 'rgba(186, 214, 242, 0.94)',
    badgeFill: 'rgba(59, 112, 168, 0.96)',
  },
  unknown: {
    edge: 'rgba(118, 126, 136, 0.52)',
    edgeWidth: 3.2,
    glow: { color: 'rgba(0, 0, 0, 0)', width: 0 },
    innerGlow: 'rgba(0, 0, 0, 0)',
    dot: '#8b97a8',
    statusText: 'rgba(188, 196, 206, 0.92)',
    badgeFill: 'rgba(86, 98, 114, 0.96)',
  },
} as const;

export const CARD_HOVER = {
  liftZ: 0.2,
  scale: 1.02,
  emissiveBoost: 0.028,
  lerp: 0.16,
} as const;

export const ellipsizeText = (
  text: string,
  maxWidth: number,
  measure: (value: string) => number,
): string => {
  if (maxWidth <= 0) return '';
  if (measure(text) <= maxWidth) return text;
  const ellipsis = '…';
  if (measure(ellipsis) > maxWidth) return ellipsis;
  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (measure(`${text.slice(0, mid)}${ellipsis}`) <= maxWidth) lo = mid;
    else hi = mid - 1;
  }
  return lo <= 0 ? ellipsis : `${text.slice(0, lo)}${ellipsis}`;
};

export const badgeRect = (
  badgeText: string,
  canvasWidth: number,
  canvasHeight: number,
) => {
  const width =
    badgeText === '--' ? 58 : badgeText.length >= 3 ? 70 : 48;
  const x = canvasWidth - CARD_BADGE.inset - width;
  const y = CARD_BADGE.inset;
  return {
    x,
    y,
    width,
    height: CARD_BADGE.height,
    radius: CARD_BADGE.radius,
    centerX: x + width / 2,
    centerY: y + CARD_BADGE.height / 2,
    canvasHeight,
  };
};

const roundRectPath = (
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) => {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
};

const hash01 = (x: number, y: number, salt: number) => {
  const n = Math.sin(x * 12.9898 + y * 78.233 + salt * 45.164) * 43758.5453;
  return n - Math.floor(n);
};

const seedFromId = (id: string) => {
  let seed = 0;
  for (let i = 0; i < id.length; i += 1) seed = (seed * 31 + id.charCodeAt(i)) >>> 0;
  return seed / 4294967295;
};

const paintFrost = (
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  seed: number,
  inset: number,
) => {
  const frostAlpha = CARD_GLASS.frostAlpha;
  const frostGain = CARD_GLASS.frostGain;
  const frostStep = CARD_GLASS.frostStep;
  for (let y = inset; y < h - inset; y += frostStep) {
    for (let x = inset; x < w - inset; x += frostStep) {
      const n = hash01(x, y, seed);
      if (n > 0.46) {
        ctx.fillStyle = `rgba(210, 224, 240, ${frostAlpha + n * frostGain})`;
        const size = n > 0.88 ? 3 : n > 0.68 ? 2 : 1;
        ctx.fillRect(x, y, size, size);
      }
    }
  }
};

const rgbaAlpha = (value: string) => {
  const match = /,\s*([0-9.]+)\)$/.exec(value);
  return match ? Number(match[1]) : 0;
};

const paintGlassEdge = (
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  tone: Application3DCardTone,
) => {
  const tokens = CARD_TONE[tone];
  const inset = CARD_GLASS.inset;
  const radius = CARD_GLASS.radius;

  if (tokens.glow.width > 0 && rgbaAlpha(tokens.glow.color) > 0) {
    ctx.save();
    ctx.shadowColor = tokens.glow.color;
    ctx.shadowBlur = tokens.glow.width;
    roundRectPath(ctx, inset, inset, w - inset * 2, h - inset * 2, radius);
    ctx.strokeStyle = tokens.glow.color;
    ctx.lineWidth = tokens.edgeWidth + 1.5;
    ctx.stroke();
    ctx.restore();
  }

  if (rgbaAlpha(tokens.innerGlow) > 0.01) {
    roundRectPath(
      ctx,
      inset + 1.5,
      inset + 1.5,
      w - inset * 2 - 3,
      h - inset * 2 - 3,
      Math.max(radius - 1.5, 0),
    );
    ctx.strokeStyle = tokens.innerGlow;
    ctx.lineWidth = Math.max(tokens.edgeWidth * 0.55, 2);
    ctx.stroke();
  }

  roundRectPath(ctx, inset, inset, w - inset * 2, h - inset * 2, radius);
  ctx.strokeStyle = tokens.edge;
  ctx.lineWidth = tokens.edgeWidth;
  ctx.stroke();
};

const paintGlassBody = (
  ctx: CanvasRenderingContext2D,
  visual: Application3DCardVisual,
  seedId: string,
) => {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const tone = visual.cardTone;
  const inset = CARD_GLASS.inset;
  const radius = CARD_GLASS.radius;
  const seed = seedFromId(seedId);

  ctx.clearRect(0, 0, w, h);

  const body = ctx.createRadialGradient(
    w / 2,
    h * 0.48,
    Math.min(w, h) * 0.08,
    w / 2,
    h * 0.5,
    Math.max(w, h) * 0.72,
  );
  if (tone === 'unknown') {
    body.addColorStop(0, CARD_GLASS.unknownBodyCenter);
    body.addColorStop(0.55, CARD_GLASS.unknownBody);
    body.addColorStop(1, CARD_GLASS.unknownBodyRim);
  } else {
    body.addColorStop(0, CARD_GLASS.bodyCenter);
    body.addColorStop(0.55, CARD_GLASS.body);
    body.addColorStop(1, CARD_GLASS.bodyRim);
  }

  roundRectPath(ctx, 0, 0, w, h, 10);
  ctx.fillStyle = body;
  ctx.fill();

  ctx.save();
  roundRectPath(ctx, inset, inset, w - inset * 2, h - inset * 2, radius);
  ctx.clip();
  ctx.fillStyle = body;
  ctx.fillRect(0, 0, w, h);
  paintFrost(ctx, w, h, seed, inset);

  const inner = ctx.createRadialGradient(w / 2, h / 2, 8, w / 2, h / 2, Math.max(w, h) * 0.62);
  inner.addColorStop(0, CARD_GLASS.innerShadow);
  inner.addColorStop(0.7, 'rgba(0, 0, 0, 0)');
  inner.addColorStop(1, 'rgba(0, 0, 0, 0)');
  ctx.fillStyle = inner;
  ctx.fillRect(0, 0, w, h);
  ctx.restore();

  paintGlassEdge(ctx, w, h, tone);
};

const paintFrontChrome = (
  ctx: CanvasRenderingContext2D,
  visual: Application3DCardVisual,
) => {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const tone = visual.cardTone;
  const tokens = CARD_TONE[tone];

  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const textShade = ctx.createRadialGradient(w / 2, h * 0.52, 8, w / 2, h * 0.52, w * 0.42);
  textShade.addColorStop(0, 'rgba(4, 8, 14, 0.16)');
  textShade.addColorStop(1, 'rgba(4, 8, 14, 0)');
  ctx.fillStyle = textShade;
  ctx.fillRect(0, h * 0.28, w, h * 0.52);
  ctx.fillStyle = tone === 'unknown' ? CARD_GLASS.titleUnknown : CARD_GLASS.title;
  ctx.font = `600 ${CARD_GLASS.titleSize}px ${CARD_GLASS.fontFamily}`;
  const title = ellipsizeText(visual.title, w - 88, (value) => ctx.measureText(value).width);
  ctx.fillText(title, w / 2, h * 0.46);

  ctx.font = `400 ${CARD_GLASS.statusSize}px ${CARD_GLASS.fontFamily}`;
  const statusY = h * 0.68;
  const labelWidth = ctx.measureText(visual.statusLabel).width;
  const dotR = 6.5;
  const gap = 8;
  const total = dotR * 2 + gap + labelWidth;
  const startX = w / 2 - total / 2;
  ctx.fillStyle = tokens.dot;
  ctx.beginPath();
  ctx.arc(startX + dotR, statusY, dotR, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = tokens.statusText;
  ctx.textAlign = 'left';
  ctx.fillText(visual.statusLabel, startX + dotR * 2 + gap, statusY);

  if (!visual.showBadge) return;
  const rect = badgeRect(visual.badgeText, w, h);
  roundRectPath(ctx, rect.x, rect.y, rect.width, rect.height, rect.radius);
  ctx.fillStyle = tokens.badgeFill;
  ctx.fill();
  ctx.fillStyle = '#ffffff';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = `600 ${CARD_BADGE.fontSize}px ${CARD_GLASS.fontFamily}`;
  ctx.fillText(visual.badgeText, rect.centerX, rect.centerY + 1);
};

export const paintApplication3DCardSide = (
  ctx: CanvasRenderingContext2D,
  tone: Application3DCardTone,
) => {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const tokens = CARD_TONE[tone];
  const bodyCenter =
    tone === 'unknown' ? CARD_GLASS.unknownBodyCenter : CARD_GLASS.bodyCenter;
  const body = tone === 'unknown' ? CARD_GLASS.unknownBody : CARD_GLASS.body;
  const bodyRim = tone === 'unknown' ? CARD_GLASS.unknownBodyRim : CARD_GLASS.bodyRim;

  ctx.clearRect(0, 0, w, h);

  const across = ctx.createLinearGradient(0, 0, w, 0);
  across.addColorStop(0, tokens.edge);
  across.addColorStop(0.16, bodyRim);
  across.addColorStop(0.5, bodyCenter);
  across.addColorStop(0.84, body);
  across.addColorStop(1, tokens.edge);
  ctx.fillStyle = across;
  ctx.fillRect(0, 0, w, h);

  const along = ctx.createLinearGradient(0, 0, 0, h);
  along.addColorStop(0, tokens.glow.color);
  along.addColorStop(0.08, 'rgba(0, 0, 0, 0)');
  along.addColorStop(0.92, 'rgba(0, 0, 0, 0)');
  along.addColorStop(1, tokens.glow.color);
  ctx.fillStyle = along;
  ctx.fillRect(0, 0, w, h);
};

const paintBackChrome = (ctx: CanvasRenderingContext2D) => {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const inset = CARD_GLASS.inset + 18;
  roundRectPath(
    ctx,
    inset,
    inset,
    w - inset * 2,
    h - inset * 2,
    Math.max(CARD_GLASS.radius - 10, 8),
  );
  ctx.fillStyle = 'rgba(22, 30, 42, 0.16)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(198, 212, 228, 0.18)';
  ctx.lineWidth = 1.8;
  ctx.stroke();
};

export const paintApplication3DCard = (
  ctx: CanvasRenderingContext2D,
  visual: Application3DCardVisual,
  seedId: string,
  face: Application3DCardFace = 'front',
) => {
  paintGlassBody(ctx, visual, seedId);
  if (face === 'back') {
    paintBackChrome(ctx);
    return;
  }
  paintFrontChrome(ctx, visual);
};
