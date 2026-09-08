export interface TooltipRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TooltipSize {
  width: number;
  height: number;
}

export const NAME_TOOLTIP_GAP = 8;
export const NAME_TOOLTIP_PAD = 8;
export const NAME_TOOLTIP_MAX_WIDTH = 240;
export const NAME_TOOLTIP_ESTIMATE_HEIGHT = 48;

export function placeTooltipAboveCard(
  card: TooltipRect,
  popover: TooltipSize,
  container: TooltipSize,
  gap = NAME_TOOLTIP_GAP,
  padding = NAME_TOOLTIP_PAD,
): { x: number; y: number } {
  const maxX = Math.max(padding, container.width - popover.width - padding);
  const centerX = card.x + card.width / 2;
  const x = Math.min(Math.max(padding, centerX - popover.width / 2), maxX);

  const above = card.y - popover.height - gap;
  const below = card.y + card.height + gap;
  const y = above >= padding ? above : Math.min(
    below,
    Math.max(padding, container.height - popover.height - padding),
  );

  return { x, y };
}
