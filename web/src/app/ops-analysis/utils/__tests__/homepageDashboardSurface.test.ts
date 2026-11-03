import { describe, expect, it } from 'vitest';
import { resolveDashboardChrome } from '../homepageDashboardSurface';

describe('resolveDashboardChrome', () => {
  it('lets the light homepage show the system background through a thin white group', () => {
    const homepage = resolveDashboardChrome(true, false);
    expect(homepage.canvasBackground).toBe('transparent');
    expect(homepage.groupBackground).toBe('rgba(255,255,255,0.46)');
    expect(homepage.groupBackdrop).toBe('blur(12px)');
    expect(homepage.groupBackground).not.toContain('portal-surface');
  });

  it('keeps the dark homepage on the operations analysis dark chrome', () => {
    expect(resolveDashboardChrome(true, true)).toEqual(resolveDashboardChrome(false, true));
  });

  it('keeps the operations analysis dashboard on the neutral chrome', () => {
    expect(resolveDashboardChrome(false, false)).toEqual({
      canvasBackground: '#f7f8fa',
      groupBackground: '#f7f8fa',
      groupHeaderBackground: '#f1f3f8',
      groupBorderColor: 'rgba(61,79,104,0.14)',
      groupHeaderBorder: '1px solid rgba(61,79,104,0.08)',
      groupBackdrop: '',
    });
    expect(resolveDashboardChrome(false, true).canvasBackground).toBe('var(--color-bg-2)');
    expect(resolveDashboardChrome(false, true).groupBackground).toBe('rgba(255,255,255,0.02)');
  });
});
