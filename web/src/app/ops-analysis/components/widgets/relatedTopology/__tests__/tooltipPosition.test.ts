import { describe, expect, it } from 'vitest';
import {
  NAME_TOOLTIP_ESTIMATE_HEIGHT,
  NAME_TOOLTIP_MAX_WIDTH,
  placeTooltipAboveCard,
} from '../tooltipPosition';

const popover = {
  width: NAME_TOOLTIP_MAX_WIDTH,
  height: NAME_TOOLTIP_ESTIMATE_HEIGHT,
};

describe('placeTooltipAboveCard', () => {
  it('centers above the card', () => {
    expect(
      placeTooltipAboveCard(
        { x: 200, y: 120, width: 200, height: 68 },
        popover,
        { width: 800, height: 400 },
      ),
    ).toEqual({ x: 180, y: 64 });
  });

  it('flips below when the top edge has no room', () => {
    expect(
      placeTooltipAboveCard(
        { x: 200, y: 12, width: 200, height: 68 },
        popover,
        { width: 800, height: 400 },
      ),
    ).toEqual({ x: 180, y: 88 });
  });
});
