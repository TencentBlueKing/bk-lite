import { theme as antdTheme } from 'antd';
import { describe, expect, it } from 'vitest';
import { defaultTheme } from '@/theme';
import {
  SCREEN_ANTD_CSS_VAR_KEY,
  buildScreenContentTokenStyle,
  createScreenAntdTheme,
} from '../screenWidgetTokens';

describe('createScreenAntdTheme', () => {
  it('returns undefined for default / missing mode', () => {
    expect(createScreenAntdTheme(undefined, defaultTheme.light)).toBeUndefined();
    expect(createScreenAntdTheme('default', defaultTheme.light)).toBeUndefined();
  });

  it('forces darkAlgorithm and isolated cssVar key for screen-dark', () => {
    const config = createScreenAntdTheme('screen-dark', defaultTheme.light);
    expect(config?.algorithm).toBe(antdTheme.darkAlgorithm);
    expect(config?.cssVar).toEqual({
      key: SCREEN_ANTD_CSS_VAR_KEY['screen-dark'],
    });
    expect(config?.token?.colorPrimary).toBe(
      defaultTheme.light.interactionPrimary,
    );
    expect(config?.token?.colorSuccess).toBe(defaultTheme.light.statusSuccess);
    expect(config?.token?.colorText).toBe('#e8eef7');
    expect(config?.token?.colorBgContainer).toBe('#14243a');
    expect(config?.components?.Segmented).toMatchObject({
      trackBg: '#14243a',
      itemSelectedBg: 'rgba(59, 130, 246, 0.2)',
    });
  });

  it('forces defaultAlgorithm for screen-light even when system tokens are dark', () => {
    const config = createScreenAntdTheme('screen-light', defaultTheme.dark);
    expect(config?.algorithm).toBe(antdTheme.defaultAlgorithm);
    expect(config?.cssVar).toEqual({
      key: SCREEN_ANTD_CSS_VAR_KEY['screen-light'],
    });
    expect(config?.token?.colorPrimary).toBe(
      defaultTheme.dark.interactionPrimary,
    );
    expect(config?.token?.colorBgElevated).toBe('rgba(255, 255, 255, 0.96)');
    expect(config?.components?.Segmented).toMatchObject({
      itemSelectedBg: '#e7effd',
    });
  });
});

describe('buildScreenContentTokenStyle', () => {
  it('remaps fill and border tokens for screen-dark', () => {
    const style = buildScreenContentTokenStyle('screen-dark') as
      | Record<string, string>
      | undefined;
    expect(style?.['--color-text-1']).toBe('#e8eef7');
    expect(style?.['--color-fill-2']).toBe('rgba(91, 143, 249, 0.12)');
    expect(style?.['--color-border-2']).toBe('rgba(112, 147, 195, 0.24)');
    expect(style?.['--chart-legend-hover-bg']).toBeUndefined();
    expect(style?.['--screen-component-switch-bg']).toBeUndefined();
  });

  it('uses selected blue as fill hover for screen-light', () => {
    const style = buildScreenContentTokenStyle('screen-light') as
      | Record<string, string>
      | undefined;
    expect(style?.['--color-fill-2']).toBe('#e7effd');
    expect(style?.['--color-primary-bg-active']).toBe('#e7effd');
  });

  it('returns undefined outside screen modes', () => {
    expect(buildScreenContentTokenStyle('default')).toBeUndefined();
  });
});
