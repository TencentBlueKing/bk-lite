import { describe, expect, it } from 'vitest';
import { buildScreenElementList } from '../screenElementList';
import { screenShapeCss } from '../screenShape';
import {
  createScreenChromeFromDrag,
  createScreenShapeItem,
} from '../screenItems';

describe('screen shape', () => {
  it('paints circle, rounded rect, border, shadow and gradient like the reference shapes', () => {
    expect(screenShapeCss('circle').borderRadius).toBe('50%');
    expect(screenShapeCss('roundedRect').borderRadius).toBe(30);
    expect(screenShapeCss('rect').borderRadius).toBe(0);
    expect(screenShapeCss('rect', { hideBorder: true }).borderStyle).toBe('none');
    expect(screenShapeCss('rect', { hideBackground: true }).background).toBe('transparent');
    expect(screenShapeCss('rect', { shadow: 0 }).boxShadow).toBe('none');
    expect(screenShapeCss('rect', { shadow: 12 }).boxShadow).toBe(
      '0 0 12px 0 rgba(255, 255, 255, 0.55)',
    );
    expect(
      screenShapeCss('rect', {
        gradient: true,
        hideBackground: false,
        gradientDirection: 'horizontal',
        gradientStart: '#111111',
        gradientEnd: '#222222',
      }).background,
    ).toBe('linear-gradient(to right, #111111 1%, #222222 100%)');
    expect(
      screenShapeCss('rect', {
        gradient: true,
        hideBackground: true,
      }).background,
    ).toBe('transparent');
    expect(
      screenShapeCss('rect', { gradient: true, gradientDirection: 'vertical' }).background,
    ).toContain('to top');
  });

  it('names duplicate shapes and creates one from a drag payload', () => {
    const first = createScreenShapeItem([], 'rect', { id: 'shape-a', zIndex: 2 });
    const second = createScreenShapeItem([first], 'rect', { id: 'shape-b', zIndex: 1 });
    const labels = buildScreenElementList([first, second], {
      shapeRect: '矩形',
      shapeCircle: '圆形',
      shapeRoundedRect: '圆角矩形',
    }).map((entry) => entry.label);
    expect(labels).toEqual(['矩形', '矩形-1']);

    const dropped = createScreenChromeFromDrag([], { kind: 'shape', shape: 'circle' });
    expect(dropped.kind).toBe('shape');
    if (dropped.kind === 'shape') {
      expect(dropped.shape).toBe('circle');
      expect(dropped.w).toBe(200);
      expect(dropped.shapeStyle.borderColor).toBe('rgba(4, 165, 180, 1)');
    }
  });
});