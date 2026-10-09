import { describe, expect, it } from 'vitest';
import {
  SCREEN_BACKGROUND_IMAGE_MAX_BYTES,
  resolveScreenCanvasBackgroundStyle,
  screenBackgroundImageRejection,
} from '../screenBackground';

const PNG_SRC = 'data:image/png;base64,iVBORw0KGgo=';

describe('resolveScreenCanvasBackgroundStyle', () => {
  it('covers a custom image and keeps it centered', () => {
    expect(
      resolveScreenCanvasBackgroundStyle({ type: 'image', src: PNG_SRC }),
    ).toEqual({
      backgroundImage: `url("${PNG_SRC}")`,
      backgroundSize: 'cover',
      backgroundPosition: 'center',
      backgroundRepeat: 'no-repeat',
    });
  });

  it('rejects a non-image or an oversized file before it is stored', () => {
    expect(screenBackgroundImageRejection({ type: 'image/gif', size: 12 })).toBe('type');
    expect(
      screenBackgroundImageRejection({
        type: 'image/png',
        size: SCREEN_BACKGROUND_IMAGE_MAX_BYTES + 1,
      }),
    ).toBe('size');
    expect(
      screenBackgroundImageRejection({
        type: 'image/jpeg',
        size: SCREEN_BACKGROUND_IMAGE_MAX_BYTES,
      }),
    ).toBeNull();
  });

  it('keeps a preset wallpaper on the canvas', () => {
    const style = resolveScreenCanvasBackgroundStyle({
      type: 'preset',
      key: 'dark-glow',
    });
    expect(style.backgroundSize).toBe('cover');
    expect(style.backgroundImage).toContain('linear-gradient');
  });

  it('keeps a solid color as a flat background', () => {
    expect(
      resolveScreenCanvasBackgroundStyle({ type: 'color', color: '#112233' }),
    ).toEqual({ background: '#112233' });
  });
});
