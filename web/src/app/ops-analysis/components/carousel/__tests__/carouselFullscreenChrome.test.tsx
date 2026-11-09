import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import CarouselFullscreenChrome from '@/app/ops-analysis/components/carousel/carouselFullscreenChrome';
import { createCarouselRemainingClock } from '@/app/ops-analysis/utils/carouselRemainingClock';
import {
  CAROUSEL_FULLSCREEN_CHROME,
  CAROUSEL_FULLSCREEN_RESUME_HINT_MS,
} from '@/app/ops-analysis/utils/carouselFullscreenChrome';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  window.sessionStorage.clear();
});

const slides = (count: number) => (
  Array.from({ length: count }, () => ({ available: true, dwellSeconds: 30 }))
);

const baseProps = () => ({
  visible: false,
  paused: false,
  slides: slides(3),
  index: 1,
  remainingMs: 15_000,
  previousLabel: '上一张',
  nextLabel: '下一张',
  playLabel: '播放',
  pauseLabel: '暂停',
  resumeHint: '空格继续',
  disableStep: false,
  disablePlay: false,
  onPrevious: vi.fn(),
  onNext: vi.fn(),
  onTogglePlay: vi.fn(),
  onHoverChange: vi.fn(),
});

const renderChrome = (
  overrides: Partial<React.ComponentProps<typeof CarouselFullscreenChrome>> = {},
) => {
  const props = { ...baseProps(), ...overrides };
  const view = render(<CarouselFullscreenChrome {...props} />);
  return { ...view, props };
};

describe('carousel fullscreen chrome', () => {
  it('stays quiet until the pointer enters the bottom-right hot zone', () => {
    const { props } = renderChrome();
    const hotzone = screen.getByTestId('carousel-fullscreen-hotzone');
    expect(hotzone.className).toContain('h-[80px]');
    expect(hotzone.className).toContain('w-[120px]');
    expect(hotzone.className).toContain('right-[16px]');
    expect(hotzone.className).toContain('bottom-[16px]');
    expect(hotzone.className).toContain('cursor-auto');
    const controls = screen.getByTestId('carousel-fullscreen-controls');
    expect(controls.className).toContain('pointer-events-none');
    expect(controls.className).toContain('h-[40px]');
    expect(controls.className).toContain('rounded-[10px]');
    expect(controls.textContent).toBe('');
    expect(screen.queryByText('2 / 3')).toBeNull();
    expect(screen.queryByText('机房总览')).toBeNull();
    expect(screen.queryByText(/剩余/)).toBeNull();
    expect(screen.queryByText(/Esc/)).toBeNull();
    expect(screen.queryByTestId('carousel-fullscreen-paused-hint')).toBeNull();
    expect(document.body.innerHTML).not.toContain('gradient-to-t');
    const progress = screen.getByTestId('carousel-fullscreen-progress');
    expect(progress.className).toContain('h-[3px]');
    fireEvent.mouseMove(hotzone);
    fireEvent.mouseEnter(hotzone);
    fireEvent.mouseLeave(hotzone);
    expect(props.onHoverChange).toHaveBeenNthCalledWith(1, true);
    expect(props.onHoverChange).toHaveBeenNthCalledWith(2, true);
    expect(props.onHoverChange).toHaveBeenNthCalledWith(3, false);
  });

  it('draws the three ghost buttons at the same weight and keeps the hold progress empty', () => {
    const { props } = renderChrome({
      visible: true,
      slides: [
        { available: false, dwellSeconds: 30 },
        { available: false, dwellSeconds: 30 },
        { available: false, dwellSeconds: 30 },
      ],
      index: -1,
      remainingMs: 0,
    });
    const buttons = [
      screen.getByRole('button', { name: '上一张' }),
      screen.getByRole('button', { name: '暂停' }),
      screen.getByRole('button', { name: '下一张' }),
    ];
    buttons.forEach((button) => {
      expect(button.className).toBe(buttons[0].className);
      expect(button.className).toContain('h-[28px]');
      expect(button.className).toContain('w-[28px]');
      expect(button.className).not.toContain('play-surface');
      expect(button.className).not.toContain('bg-white');
    });
    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[1]);
    fireEvent.click(buttons[2]);
    expect(props.onPrevious).toHaveBeenCalledOnce();
    expect(props.onTogglePlay).toHaveBeenCalledOnce();
    expect(props.onNext).toHaveBeenCalledOnce();
    expect(screen.queryByText('暂无可播放的画布')).toBeNull();
    expect(screen.queryByText(/秒后重试/)).toBeNull();
    const progress = screen.getByTestId('carousel-fullscreen-progress');
    expect(progress.querySelector('[data-tone="current"]')).toBeNull();
    expect(progress.querySelectorAll('[data-tone="unavailable"]')).toHaveLength(3);
    expect(Array.from(progress.querySelectorAll('[data-fill]')).map((node) => node.getAttribute('data-fill'))).toEqual(['0', '0', '0']);
  });

  it('switches the 3px progress at 20 and shows a one-time space hint without a top banner', () => {
    vi.useFakeTimers();
    const { rerender, props } = renderChrome({
      visible: true,
      slides: slides(20),
      index: 0,
      remainingMs: 30_000,
    });
    const progress = screen.getByTestId('carousel-fullscreen-progress');
    expect(progress.className).toContain('h-[3px]');
    expect(progress.getAttribute('data-progress-mode')).toBe('segments');
    expect(progress.querySelectorAll('[data-tone]')).toHaveLength(20);
    expect(progress.getAttribute('data-current-color')).toBe(CAROUSEL_FULLSCREEN_CHROME.current);
    expect(screen.queryByTestId('carousel-fullscreen-resume-hint')).toBeNull();

    rerender(
      <CarouselFullscreenChrome
        {...props}
        visible
        paused
        slides={slides(21)}
        index={0}
        remainingMs={30_000}
      />,
    );
    expect(screen.getByTestId('carousel-fullscreen-progress').getAttribute('data-progress-mode')).toBe('continuous');
    expect(screen.getByTestId('carousel-fullscreen-progress').getAttribute('data-current-color')).toBe(CAROUSEL_FULLSCREEN_CHROME.paused);
    const hint = screen.getByTestId('carousel-fullscreen-resume-hint');
    expect(hint.textContent).toBe('空格继续');
    expect(screen.getByTestId('carousel-fullscreen-hotzone').contains(hint)).toBe(true);
    expect(screen.queryByText('已暂停 · 按空格继续')).toBeNull();
    expect(screen.queryByTestId('carousel-fullscreen-paused-hint')).toBeNull();
    expect(screen.getByRole('button', { name: '播放' }).className).toBe(
      screen.getByRole('button', { name: '上一张' }).className,
    );
    act(() => {
      vi.advanceTimersByTime(CAROUSEL_FULLSCREEN_RESUME_HINT_MS);
    });
    expect(screen.queryByTestId('carousel-fullscreen-resume-hint')).toBeNull();
    expect(screen.getByTestId('carousel-fullscreen-controls').className).toContain('pointer-events-auto');

    rerender(
      <CarouselFullscreenChrome
        {...props}
        visible
        paused={false}
        slides={slides(21)}
      />,
    );
    rerender(
      <CarouselFullscreenChrome
        {...props}
        visible
        paused
        slides={slides(21)}
      />,
    );
    expect(screen.queryByTestId('carousel-fullscreen-resume-hint')).toBeNull();

    rerender(
      <CarouselFullscreenChrome
        {...props}
        visible
        paused
        slides={slides(21)}
        index={2}
        remainingMs={15_000}
      />,
    );
    const pausedProgress = screen.getByTestId('carousel-fullscreen-progress');
    const played = pausedProgress.querySelector('[data-part="played"]') as HTMLElement;
    const current = pausedProgress.querySelector('[data-part="current"]') as HTMLElement;
    expect(parseFloat(played.style.width)).toBeCloseTo((2 / 21) * 100);
    expect(played.style.backgroundColor).toBe('rgba(224, 242, 254, 0.92)');
    expect(parseFloat(current.style.width)).toBeCloseTo((0.5 / 21) * 100);
    expect(current.style.backgroundColor).toBe('rgb(250, 173, 20)');
    expect(played.style.backgroundColor).not.toBe(current.style.backgroundColor);
  });

  it('advances the 3px progress from the clock without rerendering the chrome owner', () => {
    const clock = createCarouselRemainingClock(15_000);
    let paints = 0;
    function Owner() {
      paints += 1;
      return <CarouselFullscreenChrome {...baseProps()} remainingMs={15_000} remainingClock={clock} />;
    }
    render(<Owner />);
    expect(screen.getByTestId('carousel-fullscreen-progress').querySelector('[data-tone="current"]')?.getAttribute('data-fill')).toBe('0.5');
    const painted = paints;
    act(() => {
      clock.set(0);
    });
    expect(paints).toBe(painted);
    expect(
      screen.getByTestId('carousel-fullscreen-progress').querySelector('[data-tone="current"]')?.getAttribute('data-fill'),
    ).toBe('1');
  });

  it('does not render an in-app Esc exit hint during carousel playback', () => {
    renderChrome({ visible: true, paused: true });
    expect(screen.queryByTestId('carousel-fullscreen-exit-hint')).toBeNull();
    expect(screen.queryByText(/Esc/)).toBeNull();
    expect(screen.queryByText('按 Esc 退出全屏')).toBeNull();
    expect(window.sessionStorage.length).toBe(0);
    expect(screen.getByTestId('carousel-fullscreen-hotzone')).toBeTruthy();
    expect(screen.getByRole('button', { name: '上一张' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '播放' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '下一张' })).toBeTruthy();
    expect(screen.getByTestId('carousel-fullscreen-progress')).toBeTruthy();
    expect(screen.getByTestId('carousel-fullscreen-resume-hint').textContent).toBe('空格继续');
  });
});
