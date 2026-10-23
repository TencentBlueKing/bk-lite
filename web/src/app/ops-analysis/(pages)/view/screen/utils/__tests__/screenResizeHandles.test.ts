import { describe, expect, it } from 'vitest';
import {
  SCREEN_EDGE_HANDLE_MIN_SCREEN_PX,
  getScreenResizeEnablement,
  readTranslatePx,
  screenGeometryFromResize,
} from '../screenResizeHandles';

describe('screen resize handles', () => {
  it('shows eight handles only while a large component is selected in edit mode', () => {
    expect(
      getScreenResizeEnablement({
        editable: true,
        selected: true,
        width: 320,
        height: 180,
        scaleX: 1,
        scaleY: 1,
      }),
    ).toEqual({
      top: true,
      right: true,
      bottom: true,
      left: true,
      topRight: true,
      bottomRight: true,
      bottomLeft: true,
      topLeft: true,
    });

    expect(
      getScreenResizeEnablement({
        editable: false,
        selected: true,
        width: 320,
        height: 180,
        scaleX: 1,
        scaleY: 1,
      }).top,
    ).toBe(false);
    expect(
      getScreenResizeEnablement({
        editable: true,
        selected: false,
        width: 320,
        height: 180,
        scaleX: 1,
        scaleY: 1,
      }).topRight,
    ).toBe(false);
  });

  it('hides an edge midpoint when that side is under 48 screen pixels', () => {
    expect(SCREEN_EDGE_HANDLE_MIN_SCREEN_PX).toBe(48);
    const narrow = getScreenResizeEnablement({
      editable: true,
      selected: true,
      width: 47,
      height: 180,
      scaleX: 1,
      scaleY: 1,
    });
    expect(narrow.top).toBe(false);
    expect(narrow.bottom).toBe(false);
    expect(narrow.left).toBe(true);
    expect(narrow.right).toBe(true);
    expect(narrow.topLeft).toBe(true);

    const short = getScreenResizeEnablement({
      editable: true,
      selected: true,
      width: 180,
      height: 80,
      scaleX: 1,
      scaleY: 0.5,
    });
    expect(short.top).toBe(true);
    expect(short.left).toBe(false);
    expect(short.right).toBe(false);
    expect(short.bottomRight).toBe(true);
  });

  it('keeps the draggable translate when react-rnd reports a scaled offset', () => {
    expect(readTranslatePx('translate(40px,12px)')).toEqual({ x: 40, y: 12 });
    expect(readTranslatePx('translate(-8px, 0px)')).toEqual({ x: -8, y: 0 });
    expect(readTranslatePx('none')).toBeNull();

    expect(
      screenGeometryFromResize(
        {
          style: { transform: 'translate(10px,12px)' },
          offsetWidth: 100.4,
          offsetHeight: 48.6,
        },
        { x: 10, y: 99 },
      ),
    ).toEqual({ x: 10, y: 12, w: 100, h: 49 });

    expect(
      screenGeometryFromResize(
        {
          style: { transform: '' },
          offsetWidth: 140,
          offsetHeight: 40,
        },
        { x: -30.2, y: 20.4 },
      ),
    ).toEqual({ x: -30, y: 20, w: 140, h: 40 });
  });
});
