import type { Application3DCardTone, Application3DCardVisual } from './application3DLayout';

/**
 * The painted texture is the on-screen glass. Face shader only samples it.
 * Plate is a dark translucent fill; status color lives in a soft bloom edge.
 */
export const CARD_THICKNESS = 0.16;

export type Application3DCardFace = 'front' | 'back';

export const CARD_GLASS = {
  radius: 24,
  inset: 10,
  bodyCenter: 'rgba(16, 32, 48, 0.58)',
  body: 'rgba(10, 22, 36, 0.64)',
  bodyRim: 'rgba(8, 16, 28, 0.7)',
  unknownBodyCenter: 'rgba(20, 24, 32, 0.56)',
  unknownBody: 'rgba(14, 18, 26, 0.62)',
  unknownBodyRim: 'rgba(10, 14, 20, 0.68)',
  innerShadow: 'rgba(0, 0, 0, 0.16)',
  sheen: 'rgba(255, 255, 255, 0.16)',
  sheenFade: 'rgba(198, 214, 232, 0.06)',
  title: 'rgba(248, 250, 252, 0.96)',
  titleUnknown: 'rgba(198, 204, 214, 0.9)',
  frostAlpha: 0,
  frostGain: 0,
  frostStep: 8,
  fontFamily: '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif',
  titleSize: 48,
  statusSize: 42,
  iconSize: 64,
} as const;

export const CARD_BADGE = {
  height: 44,
  radius: 8,
  fontSize: 26,
  inset: 22,
} as const;

export const CARD_TONE = {
  normal: {
    edge: 'rgba(92, 154, 190, 0.3)',
    edgeWidth: 0.7,
    glow: { color: 'rgba(64, 136, 180, 0.22)', width: 11 },
    innerGlow: 'rgba(152, 196, 224, 0.14)',
    wash: 'rgba(20, 52, 82, 0.08)',
    statusFill: 'rgba(6, 12, 20, 0.72)',
    statusStroke: 'rgba(150, 176, 194, 0.28)',
    statusText: 'rgba(226, 232, 238, 0.96)',
    icon: 'rgba(236, 240, 246, 0.96)',
    badgeFill: 'rgba(4, 8, 14, 0.78)',
    badgeBorder: 'rgba(0, 0, 0, 0)',
    tint: 0x5a92b4,
  },
  critical: {
    edge: 'rgba(255, 96, 86, 0.42)',
    edgeWidth: 1.15,
    glow: { color: 'rgba(255, 70, 58, 0.22)', width: 17 },
    innerGlow: 'rgba(255, 170, 160, 0.14)',
    wash: 'rgba(140, 22, 16, 0.07)',
    statusFill: 'rgba(28, 8, 8, 0.74)',
    statusStroke: 'rgba(255, 110, 96, 0.5)',
    statusText: 'rgba(255, 168, 158, 0.96)',
    icon: 'rgba(236, 240, 246, 0.96)',
    badgeFill: 'rgba(10, 4, 4, 0.78)',
    badgeBorder: 'rgba(0, 0, 0, 0)',
    tint: 0xff5c4e,
  },
  warning: {
    edge: 'rgba(255, 176, 80, 0.36)',
    edgeWidth: 0.95,
    glow: { color: 'rgba(255, 160, 56, 0.18)', width: 13 },
    innerGlow: 'rgba(255, 210, 150, 0.13)',
    wash: 'rgba(150, 72, 16, 0.05)',
    statusFill: 'rgba(26, 12, 4, 0.74)',
    statusStroke: 'rgba(255, 172, 80, 0.48)',
    statusText: 'rgba(255, 198, 126, 0.96)',
    icon: 'rgba(236, 240, 246, 0.96)',
    badgeFill: 'rgba(10, 6, 2, 0.78)',
    badgeBorder: 'rgba(0, 0, 0, 0)',
    tint: 0xffa848,
  },
  error: {
    edge: 'rgba(255, 110, 90, 0.4)',
    edgeWidth: 1.05,
    glow: { color: 'rgba(255, 80, 64, 0.2)', width: 15 },
    innerGlow: 'rgba(255, 176, 164, 0.13)',
    wash: 'rgba(132, 24, 18, 0.06)',
    statusFill: 'rgba(26, 8, 8, 0.74)',
    statusStroke: 'rgba(255, 118, 102, 0.48)',
    statusText: 'rgba(255, 176, 164, 0.96)',
    icon: 'rgba(236, 240, 246, 0.96)',
    badgeFill: 'rgba(10, 4, 4, 0.78)',
    badgeBorder: 'rgba(0, 0, 0, 0)',
    tint: 0xff6050,
  },
  info: {
    edge: 'rgba(120, 190, 230, 0.32)',
    edgeWidth: 0.85,
    glow: { color: 'rgba(80, 170, 220, 0.16)', width: 9 },
    innerGlow: 'rgba(176, 220, 246, 0.1)',
    wash: 'rgba(24, 80, 120, 0.04)',
    statusFill: 'rgba(6, 14, 22, 0.72)',
    statusStroke: 'rgba(148, 184, 210, 0.3)',
    statusText: 'rgba(220, 230, 238, 0.94)',
    icon: 'rgba(236, 240, 246, 0.96)',
    badgeFill: 'rgba(4, 8, 14, 0.76)',
    badgeBorder: 'rgba(0, 0, 0, 0)',
    tint: 0x80b4d2,
  },
  unknown: {
    edge: 'rgba(118, 126, 136, 0.34)',
    edgeWidth: 0.78,
    glow: { color: 'rgba(130, 140, 152, 0.1)', width: 7 },
    innerGlow: 'rgba(186, 196, 210, 0.08)',
    wash: 'rgba(16, 18, 24, 0.03)',
    statusFill: 'rgba(10, 12, 16, 0.7)',
    statusStroke: 'rgba(156, 166, 180, 0.24)',
    statusText: 'rgba(206, 212, 220, 0.92)',
    icon: 'rgba(220, 226, 234, 0.88)',
    badgeFill: 'rgba(8, 10, 14, 0.74)',
    badgeBorder: 'rgba(0, 0, 0, 0)',
    tint: 0x96a0ae,
  },
} as const;

export const CARD_HOVER = {
  liftZ: 0.28,
  scale: 1.03,
  emissiveBoost: 0.04,
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
    badgeText === '--' ? 62 : badgeText.length >= 3 ? 66 : 50;
  const x = canvasWidth - CARD_BADGE.inset - width;
  const y = CARD_BADGE.inset - 2;
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

const rgbaAlpha = (value: string) => {
  const match = /,\s*([0-9.]+)\)$/.exec(value);
  return match ? Number(match[1]) : 0;
};

const paintGlassBody = (ctx: CanvasRenderingContext2D) => {
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
};

const paintCubeIcon = (
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  size: number,
  color: string,
) => {
  const dx = size * 0.46;
  const dy = size * 0.26;
  const drop = size * 0.46;
  const x = cx;
  const y = cy - drop / 2;
  const top = { x, y: y - dy };
  const right = { x: x + dx, y };
  const bottom = { x, y: y + dy };
  const left = { x: x - dx, y };
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = Math.max(2.4, size * 0.07);
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(top.x, top.y);
  ctx.lineTo(right.x, right.y);
  ctx.lineTo(bottom.x, bottom.y);
  ctx.lineTo(left.x, left.y);
  ctx.closePath();
  ctx.moveTo(left.x, left.y);
  ctx.lineTo(left.x, left.y + drop);
  ctx.lineTo(bottom.x, bottom.y + drop);
  ctx.lineTo(right.x, right.y + drop);
  ctx.lineTo(right.x, right.y);
  ctx.moveTo(bottom.x, bottom.y);
  ctx.lineTo(bottom.x, bottom.y + drop);
  ctx.stroke();
  const stemX = x - dx * 0.18;
  const stemTop = y - dy * 0.08;
  const stemBot = y + drop * 0.42;
  ctx.beginPath();
  ctx.moveTo(stemX, stemBot);
  ctx.lineTo(stemX, stemTop);
  ctx.moveTo(stemX, stemTop + size * 0.12);
  ctx.lineTo(stemX - size * 0.12, stemTop + size * 0.02);
  ctx.moveTo(stemX, stemTop + size * 0.2);
  ctx.lineTo(stemX + size * 0.1, stemTop + size * 0.08);
  ctx.stroke();
  ctx.restore();
};

const paintFrontChrome = (
  ctx: CanvasRenderingContext2D,
  visual: Application3DCardVisual,
) => {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const tone = visual.cardTone;
  const tokens = CARD_TONE[tone];
  const padX = 40;
  const headerY = 108;
  const iconSize = CARD_GLASS.iconSize;
  const iconX = padX + iconSize * 0.46;
  paintCubeIcon(ctx, iconX, headerY, iconSize, tokens.icon);

  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = tone === 'unknown' ? CARD_GLASS.titleUnknown : CARD_GLASS.title;
  ctx.font = `600 ${CARD_GLASS.titleSize}px ${CARD_GLASS.fontFamily}`;
  const badge = visual.showBadge ? badgeRect(visual.badgeText, w, h) : null;
  const titleX = iconX + iconSize * 0.46 + 28;
  const titleMax = (badge ? badge.x - 16 : w - padX) - titleX;
  const title = ellipsizeText(visual.title, titleMax, (value) => ctx.measureText(value).width);
  ctx.fillText(title, titleX, headerY);

  ctx.font = `500 ${CARD_GLASS.statusSize}px ${CARD_GLASS.fontFamily}`;
  const statusWidth = ctx.measureText(visual.statusLabel).width;
  const tagPadX = 20;
  const tagH = 56;
  const tagW = statusWidth + tagPadX * 2;
  const tagX = padX;
  const tagY = headerY + 72;
  const tagGlow = tone === 'normal' || tone === 'unknown' || tone === 'info' ? 0 : 4;
  if (tagGlow > 0) {
    ctx.save();
    ctx.shadowColor = tokens.glow.color;
    ctx.shadowBlur = tagGlow;
    roundRectPath(ctx, tagX, tagY, tagW, tagH, 7);
    ctx.fillStyle = tokens.statusFill;
    ctx.fill();
    ctx.restore();
  }
  roundRectPath(ctx, tagX, tagY, tagW, tagH, 7);
  ctx.fillStyle = tokens.statusFill;
  ctx.fill();
  ctx.strokeStyle = tokens.statusStroke;
  ctx.lineWidth = 0.9;
  ctx.stroke();
  ctx.fillStyle = tokens.statusText;
  ctx.fillText(visual.statusLabel, tagX + tagPadX, tagY + tagH / 2 + 1);

  if (!visual.showBadge || !badge) return;
  roundRectPath(ctx, badge.x, badge.y, badge.width, badge.height, badge.radius);
  ctx.fillStyle = tokens.badgeFill;
  ctx.fill();
  if (rgbaAlpha(tokens.badgeBorder) > 0.02) {
    ctx.strokeStyle = tokens.badgeBorder;
    ctx.lineWidth = 0.8;
    ctx.stroke();
  }
  ctx.fillStyle = 'rgba(236, 240, 246, 0.96)';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = `500 ${CARD_BADGE.fontSize}px ${CARD_GLASS.fontFamily}`;
  ctx.fillText(visual.badgeText, badge.centerX, badge.centerY + 1);
};

export const paintApplication3DCardSide = (
  ctx: CanvasRenderingContext2D,
  tone: Application3DCardTone,
) => {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const bodyCenter =
    tone === 'unknown' ? CARD_GLASS.unknownBodyCenter : CARD_GLASS.bodyCenter;
  const body = tone === 'unknown' ? CARD_GLASS.unknownBody : CARD_GLASS.body;
  const bodyRim = tone === 'unknown' ? CARD_GLASS.unknownBodyRim : CARD_GLASS.bodyRim;

  ctx.clearRect(0, 0, w, h);

  const across = ctx.createLinearGradient(0, 0, w, 0);
  across.addColorStop(0, bodyRim);
  across.addColorStop(0.5, bodyCenter);
  across.addColorStop(1, body);
  ctx.fillStyle = across;
  ctx.fillRect(0, 0, w, h);

  const lip = ctx.createLinearGradient(0, 0, 0, h);
  lip.addColorStop(0, 'rgba(8, 16, 28, 0.2)');
  lip.addColorStop(0.72, 'rgba(18, 40, 58, 0.08)');
  lip.addColorStop(1, tone === 'unknown' ? 'rgba(186, 196, 210, 0.28)' : 'rgba(142, 184, 210, 0.3)');
  ctx.fillStyle = lip;
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
  paintGlassBody(ctx);
  if (face === 'back') {
    paintBackChrome(ctx);
    return;
  }
  paintFrontChrome(ctx, visual);
};
