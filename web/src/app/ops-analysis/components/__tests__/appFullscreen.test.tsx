import { useRef, useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import en from '@/locales/en.json';
import zh from '@/locales/zh.json';
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '@/app/ops-analysis/components/appFullscreen';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('AppViewFullscreenExit', () => {
  it('shows an Esc tip for 3 seconds after entering fullscreen, then hides it', () => {
    vi.useFakeTimers();
    render(<AppViewFullscreenExit visible onExit={() => undefined} />);

    expect(screen.getByRole('status').textContent).toBe('common.pressEscToExitFullscreen');

    act(() => {
      vi.advanceTimersByTime(2999);
    });
    expect(screen.queryByRole('status')).not.toBeNull();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('clears the tip timer when fullscreen closes or the chrome unmounts', () => {
    vi.useFakeTimers();
    const view = render(<AppViewFullscreenExit visible onExit={() => undefined} />);

    view.rerender(<AppViewFullscreenExit visible={false} onExit={() => undefined} />);
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.queryByRole('status')).toBeNull();

    view.rerender(<AppViewFullscreenExit visible onExit={() => undefined} />);
    expect(screen.getByRole('status')).not.toBeNull();
    view.unmount();
    act(() => {
      vi.advanceTimersByTime(3000);
    });
  });

  it('reveals the exit button only while the top-right corner is hovered', () => {
    const onExit = vi.fn();
    render(<AppViewFullscreenExit visible onExit={onExit} />);

    const hotZone = screen.getByTestId('app-view-fullscreen-exit-hotzone');
    const buttonShell = screen.getByTestId('app-view-fullscreen-exit-button');
    expect(buttonShell.getAttribute('data-shown')).toBe('false');
    expect(screen.queryByRole('button', { name: 'common.exitFullscreen' })).toBeNull();

    fireEvent.mouseEnter(hotZone);
    const exitButton = screen.getByRole('button', { name: 'common.exitFullscreen' });
    expect(buttonShell.getAttribute('data-shown')).toBe('true');
    fireEvent.click(exitButton);
    expect(onExit).toHaveBeenCalledTimes(1);

    fireEvent.mouseLeave(hotZone);
    expect(buttonShell.getAttribute('data-shown')).toBe('false');
    expect(screen.queryByRole('button', { name: 'common.exitFullscreen' })).toBeNull();
  });

  it('does not remount a sibling canvas when the tip hides', () => {
    vi.useFakeTimers();
    const instances = { current: 0 };

    const Canvas = () => {
      const instanceId = useRef<number | null>(null);
      if (instanceId.current === null) {
        instances.current += 1;
        instanceId.current = instances.current;
      }
      return <div data-testid="canvas" data-instance={instanceId.current} />;
    };

    const Host = () => {
      const [filter, setFilter] = useState('region=a');
      const { isFullscreen, enterFullscreen, exitFullscreen } = useAppViewFullscreen();
      return (
        <div>
          <div data-testid="filter">{filter}</div>
          <button type="button" onClick={() => setFilter('region=b')}>change-filter</button>
          <button type="button" onClick={enterFullscreen}>enter</button>
          <Canvas />
          <AppViewFullscreenExit visible={isFullscreen} onExit={exitFullscreen} />
        </div>
      );
    };

    render(<Host />);
    fireEvent.click(screen.getByRole('button', { name: 'enter' }));
    fireEvent.click(screen.getByRole('button', { name: 'change-filter' }));
    expect(screen.getByTestId('filter').textContent).toBe('region=b');
    expect(screen.getByRole('status').textContent).toBe('common.pressEscToExitFullscreen');
    expect(screen.getByTestId('canvas').getAttribute('data-instance')).toBe('1');

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.getByTestId('canvas').getAttribute('data-instance')).toBe('1');
    expect(instances.current).toBe(1);

    fireEvent.mouseEnter(screen.getByTestId('app-view-fullscreen-exit-hotzone'));
    fireEvent.click(screen.getByRole('button', { name: 'common.exitFullscreen' }));
    expect(screen.queryByTestId('app-view-fullscreen-esc-tip')).toBeNull();
    expect(screen.getByTestId('filter').textContent).toBe('region=b');
    expect(screen.getByTestId('canvas').getAttribute('data-instance')).toBe('1');
  });
});

describe('useAppViewFullscreen', () => {
  it('keeps Escape exit and does not call the browser Fullscreen API', () => {
    const requestFullscreen = vi.fn();
    Object.defineProperty(document.documentElement, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    });
    Object.defineProperty(HTMLElement.prototype, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    });

    const Harness = () => {
      const { isFullscreen, enterFullscreen } = useAppViewFullscreen();
      return (
        <button type="button" data-state={isFullscreen ? 'on' : 'off'} onClick={enterFullscreen}>
          toggle
        </button>
      );
    };

    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'toggle' }));
    expect(screen.getByRole('button', { name: 'toggle' }).getAttribute('data-state')).toBe('on');
    expect(requestFullscreen).not.toHaveBeenCalled();

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(screen.getByRole('button', { name: 'toggle' }).getAttribute('data-state')).toBe('off');
    expect(requestFullscreen).not.toHaveBeenCalled();
  });
});

describe('fullscreen exit copy and screen mount', () => {
  it('adds the Esc tip in Chinese and English', () => {
    expect(zh.common.pressEscToExitFullscreen).toBe('按 Esc 退出全屏');
    expect(en.common.pressEscToExitFullscreen).toBe('Press Esc to exit fullscreen');
  });

  it('mounts the shared exit chrome inside the screen fullscreen shell', () => {
    const source = readFileSync(
      path.resolve(process.cwd(), 'src/app/ops-analysis/(pages)/view/screen/index.tsx'),
      'utf8',
    );
    expect(source).toContain(
      '<AppViewFullscreenExit visible={isFullscreen} onExit={exitFullscreen} />',
    );
    expect(source).not.toContain('requestFullscreen');
  });
});
