import type { CSSProperties } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import {
  DecorationSkin,
  ScreenChromeSkinStyles,
  TitleFrameSkin,
} from './screenChromeSkins';
import { getScreenClockDisplayParts } from '../utils/screenClock';
import { getScreenTheme } from '../utils/screenTheme';
import { resolveScreenCanvasBackgroundStyle } from '../utils/screenBackground';
import {
  SCREEN_DIVIDER_PRESETS,
  SCREEN_PANEL_FRAME_PRESETS,
  TITLE_FRAME_PRESETS,
} from '../utils/screenItems';

const theme = getScreenTheme('screen-dark');
const boardStyle = {
  ...theme.variables,
  isolation: 'isolate',
  backgroundColor: '#071422',
  ...resolveScreenCanvasBackgroundStyle(
    { type: 'preset', key: 'dark-glow' },
    'screen-dark',
  ),
} as CSSProperties;

const clock = getScreenClockDisplayParts(
  new Date(2026, 8, 20, 16, 7, 9),
  'dddd HH:mm:ss',
);

const meta: Meta = {
  title: 'ops-analysis/ScreenChromeSkins',
};

export default meta;

export const LockedVisionSkins: StoryObj = {
  render: () => (
    <div
      className="relative isolate min-h-[640px] w-[1100px] overflow-hidden p-8 text-(--screen-title-color)"
      style={boardStyle}
    >
      <ScreenChromeSkinStyles />
      <div className="mb-8 flex items-start justify-between gap-8">
        <div className="h-[70px] w-[750px]">
          <TitleFrameSkin item={{ preset: 'hero-1', content: '运营大屏' }} />
        </div>
        <div className="flex h-[56px] shrink-0 items-center gap-2">
          <span className="text-[13px] text-(--screen-clock-color)">
            {clock.date}
          </span>
          <span className="text-[13px] text-(--screen-clock-color)">
            {clock.week}
          </span>
          <span className="text-[28px] font-semibold tracking-[0.12em] tabular-nums">
            {clock.primary}
          </span>
        </div>
      </div>
      <div className="mb-8 flex flex-col gap-4">
        <div className="h-9 w-[400px]">
          <TitleFrameSkin item={{ preset: 'section-1', content: '数据概览' }} />
        </div>
        <div className="h-9 w-[400px]">
          <TitleFrameSkin item={{ preset: 'section-2', content: '数据概览' }} />
        </div>
      </div>
      <div
        className="relative mb-8 h-[70px] w-[750px]"
        style={{ outline: '1px dashed var(--screen-chrome-accent)' }}
      >
        <TitleFrameSkin item={{ preset: 'hero-2', content: '运营大屏' }} />
        {(['-4px -4px auto auto', 'auto -4px -4px auto', 'auto auto -4px -4px', '-4px auto auto -4px'] as const).map(
          (inset) => (
            <i
              key={inset}
              className="absolute h-2 w-2 border border-(--screen-chrome-accent) bg-(--screen-title-color)"
              style={{ inset }}
            />
          ),
        )}
      </div>
      <div className="mb-8 grid grid-cols-3 gap-4">
        {SCREEN_PANEL_FRAME_PRESETS.map(
          (preset) => (
            <div key={preset} className="h-[160px]">
              <DecorationSkin item={{ decorationType: 'panelFrame', preset }} />
            </div>
          ),
        )}
      </div>
      <div className="mb-8 flex flex-col gap-3">
        {SCREEN_DIVIDER_PRESETS.map((preset) => (
          <div key={preset} className="h-7 w-[420px]">
            <DecorationSkin item={{ decorationType: 'divider', preset }} />
          </div>
        ))}
      </div>
      <div className="mb-8 flex gap-6">
        <section className="relative h-[160px] w-[280px] border border-(--screen-widget-border) bg-(--screen-widget-bg)">
          <header className="flex h-[34px] items-center border-b border-(--screen-widget-header-border) bg-(--screen-widget-header-bg) pl-4 text-sm font-bold shadow-[inset_2px_0_0_var(--screen-chrome-accent)]">
            CPU 使用率
          </header>
        </section>
        <section className="relative h-[160px] w-[280px] border border-transparent">
          <header className="flex h-[34px] items-center border-b border-(--screen-widget-header-border) pl-3 text-sm font-bold">
            趋势
          </header>
        </section>
      </div>
      <div className="mt-6 text-xs text-(--screen-clock-color)">
        {TITLE_FRAME_PRESETS.join(' / ')}
      </div>
    </div>
  ),
};
