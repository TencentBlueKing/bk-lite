import { describe, expect, it } from 'vitest';
import {
  SCREEN_DIVIDER_PRESETS,
  SCREEN_PANEL_FRAME_PRESETS,
  TITLE_FRAME_PRESETS,
  resolveDividerPreset,
  resolvePanelFramePreset,
} from '../screenItems';

describe('screen auxiliary catalog', () => {
  it('offers title frames, hollow borders, and dividers', () => {
    expect(TITLE_FRAME_PRESETS).toEqual([
      'hero-1',
      'hero-2',
      'hero-3',
      'hero-4',
      'hero-5',
      'hero-6',
      'section-1',
      'section-2',
      'section-3',
      'section-4',
    ]);
    expect(SCREEN_PANEL_FRAME_PRESETS).toEqual([
      'border-21',
      'border-22',
      'border-23',
      'border-25',
      'border-1',
      'tech',
      'border-16',
      'border-20',
      'border-24',
    ]);
    expect(SCREEN_DIVIDER_PRESETS).toEqual([
      'line-1',
      'line-2',
      'line-3',
      'line-dec',
      'line-4',
    ]);
  });

  it('reads the old two-preset ids as the first matching skin', () => {
    expect(resolvePanelFramePreset('a')).toBe('border-21');
    expect(resolvePanelFramePreset('b')).toBe('tech');
    expect(resolvePanelFramePreset('border-25')).toBe('border-25');
    expect(resolvePanelFramePreset(undefined)).toBe('border-21');
    expect(resolveDividerPreset('a')).toBe('line-1');
    expect(resolveDividerPreset('b')).toBe('line-dec');
    expect(resolveDividerPreset('line-2')).toBe('line-2');
  });
});
