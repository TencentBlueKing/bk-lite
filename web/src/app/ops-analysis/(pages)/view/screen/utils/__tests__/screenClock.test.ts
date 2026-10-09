import { describe, expect, it } from 'vitest';
import { formatScreenClockByPreset, getScreenClockDisplayParts } from '../screenClock';

describe('formatScreenClockByPreset', () => {
  const date = new Date(2026, 8, 20, 16, 7, 9);

  it('formats the locked clock presets from local time', () => {
    expect(formatScreenClockByPreset(date, 'HH:mm:ss')).toBe('16:07:09');
    expect(formatScreenClockByPreset(date, 'YYYY-MM-DD')).toBe('2026-09-20');
    expect(formatScreenClockByPreset(date, 'YYYY-MM-DD HH:mm:ss')).toBe(
      '2026-09-20 16:07:09',
    );
    expect(formatScreenClockByPreset(date, 'YYYY年M月D日')).toBe('2026年9月20日');
    expect(formatScreenClockByPreset(date, 'M月D日 HH:mm')).toBe('9月20日 16:07');
    expect(formatScreenClockByPreset(date, 'dddd HH:mm:ss')).toBe(
      '2026-09-20 星期日 16:07:09',
    );
  });

  it('splits Vision-style clock parts for canvas rendering', () => {
    expect(getScreenClockDisplayParts(date, 'YYYY-MM-DD HH:mm:ss')).toEqual({
      date: '2026-09-20',
      primary: '16:07:09',
    });
    expect(getScreenClockDisplayParts(date, 'dddd HH:mm:ss')).toEqual({
      date: '2026.09.20',
      week: '星期日',
      primary: '16:07:09',
    });
  });
});
