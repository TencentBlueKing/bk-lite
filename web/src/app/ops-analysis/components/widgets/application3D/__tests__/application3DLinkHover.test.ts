import { describe, expect, it } from 'vitest';
import {
  application3DHoverReadableScale,
  placeSceneHoverPopup,
  shouldShowApplication3DLinkHover,
} from '../application3DLinkHover';

describe('shouldShowApplication3DLinkHover', () => {
  const hint = '右键打开链接';

  it('shows for link-menu objects only while the hint is active and the menu is closed', () => {
    expect(shouldShowApplication3DLinkHover(hint, 'wall', false)).toBe(true);
    expect(shouldShowApplication3DLinkHover(hint, 'host', false)).toBe(true);
    expect(shouldShowApplication3DLinkHover(hint, 'system', false)).toBe(true);
    expect(shouldShowApplication3DLinkHover(hint, 'application', false)).toBe(true);
    expect(shouldShowApplication3DLinkHover(hint, 'cabinet', false)).toBe(false);
    expect(shouldShowApplication3DLinkHover('', 'wall', false)).toBe(false);
    expect(shouldShowApplication3DLinkHover(undefined, 'host', false)).toBe(false);
    expect(shouldShowApplication3DLinkHover(hint, 'wall', true)).toBe(false);
  });
});

describe('application3D hover popup placement', () => {
  it('follows the readable screen scale and stays inside the widget', () => {
    expect(application3DHoverReadableScale(undefined)).toBe(1);
    expect(application3DHoverReadableScale({
      enabled: true,
      fitScale: 0.5,
      widgetUiScale: 1,
      screenUiScale: 1,
    })).toBe(2);
    expect(application3DHoverReadableScale({
      enabled: false,
      fitScale: 0.5,
      widgetUiScale: 1,
      screenUiScale: 1,
    })).toBe(1);

    const nearCursor = placeSceneHoverPopup({
      clientX: 40,
      clientY: 30,
      anchorLeft: 0,
      anchorTop: 0,
      anchorWidth: 320,
      anchorHeight: 180,
      offsetWidth: 320,
      offsetHeight: 180,
      popupWidth: 80,
      popupHeight: 40,
      readableScale: 1,
    });
    expect(nearCursor).toEqual({ left: 46, top: 36 });

    const scaled = placeSceneHoverPopup({
      clientX: 20,
      clientY: 10,
      anchorLeft: 0,
      anchorTop: 0,
      anchorWidth: 160,
      anchorHeight: 90,
      offsetWidth: 320,
      offsetHeight: 180,
      popupWidth: 80,
      popupHeight: 40,
      readableScale: 2,
    });
    expect(scaled.left).toBe(52);
    expect(scaled.top).toBe(32);

    const flipped = placeSceneHoverPopup({
      clientX: 300,
      clientY: 160,
      anchorLeft: 0,
      anchorTop: 0,
      anchorWidth: 320,
      anchorHeight: 180,
      offsetWidth: 320,
      offsetHeight: 180,
      popupWidth: 80,
      popupHeight: 40,
    });
    expect(flipped.left).toBe(214);
    expect(flipped.top).toBe(132);
  });
});
