'use client';

import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { CarouselRemainingClock } from '@/app/ops-analysis/utils/carouselRemainingClock';
import {
  CaretRightOutlined,
  LeftOutlined,
  PauseOutlined,
  RightOutlined,
} from '@ant-design/icons';
import {
  CAROUSEL_FULLSCREEN_CHROME,
  CAROUSEL_FULLSCREEN_EXIT_TIP_MS,
  CAROUSEL_FULLSCREEN_RESUME_HINT_MS,
  markFullscreenExitTipSeen,
  readFullscreenExitTipSeen,
  resolveCarouselFullscreenProgress,
  type FullscreenSlideProgressInput,
} from '@/app/ops-analysis/utils/carouselFullscreenChrome';

const chromeVars = {
  '--carousel-fs-surface': CAROUSEL_FULLSCREEN_CHROME.surface,
  '--carousel-fs-border': CAROUSEL_FULLSCREEN_CHROME.border,
  '--carousel-fs-ink': CAROUSEL_FULLSCREEN_CHROME.ink,
  '--carousel-fs-hover': CAROUSEL_FULLSCREEN_CHROME.hover,
  '--carousel-fs-track': CAROUSEL_FULLSCREEN_CHROME.track,
  '--carousel-fs-upcoming': CAROUSEL_FULLSCREEN_CHROME.upcoming,
} as React.CSSProperties;

const ghostButtonClassName = 'inline-flex shrink-0 cursor-pointer items-center justify-center rounded-md border border-transparent bg-transparent p-0 text-(--carousel-fs-ink) transition-colors hover:border-(--carousel-fs-border) hover:bg-(--carousel-fs-hover) disabled:cursor-not-allowed disabled:opacity-40';

const hintClassName = 'pointer-events-none rounded-[10px] border border-(--carousel-fs-border) bg-(--carousel-fs-surface) px-2.5 py-1 text-xs leading-none text-(--carousel-fs-ink) backdrop-blur-[12px]';

const subscribeToNothing = () => () => undefined;

/** 连续条按序号铺开：已过的部分保持亮色，只有当前这一段用播放色或暂停琥珀色。 */
const ContinuousProgress: React.FC<{
  segments: readonly { tone: string; fill: number }[];
  currentColor: string;
}> = ({ segments, currentColor }) => {
  const count = segments.length || 1;
  const currentIndex = segments.findIndex((segment) => segment.tone === 'current');
  const playedRatio = currentIndex >= 0 ? currentIndex / count : 0;
  const currentRatio = currentIndex >= 0 ? segments[currentIndex].fill / count : 0;
  return (
    <div className="relative h-full w-full">
      <div
        className="absolute inset-y-0 left-0"
        data-part="played"
        data-fill={playedRatio}
        style={{
          width: `${playedRatio * 100}%`,
          backgroundColor: CAROUSEL_FULLSCREEN_CHROME.played,
        }}
      />
      <div
        className="absolute inset-y-0"
        data-part="current"
        data-fill={currentRatio}
        style={{
          left: `${playedRatio * 100}%`,
          width: `${currentRatio * 100}%`,
          backgroundColor: currentColor,
        }}
      />
    </div>
  );
};

const CarouselFullscreenProgress: React.FC<{
  slides: readonly FullscreenSlideProgressInput[];
  index: number;
  paused: boolean;
  remainingMs: number;
  remainingClock?: CarouselRemainingClock;
}> = ({
  slides,
  index,
  paused,
  remainingMs,
  remainingClock,
}) => {
  const liveRemaining = useSyncExternalStore(
    remainingClock ? remainingClock.subscribe : subscribeToNothing,
    () => (remainingClock ? remainingClock.getSnapshot() : remainingMs),
    () => (remainingClock ? remainingClock.getSnapshot() : remainingMs),
  );
  const progress = resolveCarouselFullscreenProgress({
    slides,
    index,
    remainingMs: liveRemaining,
    paused,
  });
  return (
    <div
      className="pointer-events-none absolute inset-x-0 bottom-0 h-[3px] bg-(--carousel-fs-track)"
      data-testid="carousel-fullscreen-progress"
      data-progress-mode={progress.mode}
      data-current-color={progress.currentColor}
      aria-hidden
    >
      {progress.mode === 'segments' ? (
        <div className="flex h-full gap-0.5">
          {progress.segments.map((segment, segmentIndex) => (
            <div
              key={segmentIndex}
              className={`relative h-full min-w-0 flex-1 overflow-hidden ${
                segment.tone === 'unavailable'
                  ? 'bg-[repeating-linear-gradient(135deg,rgba(255,255,255,0.28)_0_3px,rgba(255,255,255,0.08)_3px_7px)]'
                  : 'bg-(--carousel-fs-upcoming)'
              }`}
              data-tone={segment.tone}
              data-fill={segment.fill}
            >
              {segment.tone === 'played' || segment.tone === 'current' ? (
                <div
                  className="absolute inset-y-0 left-0 w-full origin-left transition-transform duration-200 ease-linear"
                  style={{
                    transform: `scaleX(${segment.fill})`,
                    backgroundColor: segment.tone === 'played'
                      ? CAROUSEL_FULLSCREEN_CHROME.played
                      : progress.currentColor,
                  }}
                />
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <ContinuousProgress
          segments={progress.segments}
          currentColor={progress.currentColor}
        />
      )}
    </div>
  );
};

export interface CarouselFullscreenChromeProps {
  visible: boolean;
  paused: boolean;
  slides: readonly FullscreenSlideProgressInput[];
  index: number;
  remainingMs: number;
  remainingClock?: CarouselRemainingClock;
  previousLabel: string;
  nextLabel: string;
  playLabel: string;
  pauseLabel: string;
  resumeHint: string;
  exitHint: string;
  disableStep: boolean;
  disablePlay: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onTogglePlay: () => void;
  onHoverChange: (hovering: boolean) => void;
}

const CarouselFullscreenChrome: React.FC<CarouselFullscreenChromeProps> = ({
  visible,
  paused,
  slides,
  index,
  remainingMs,
  remainingClock,
  previousLabel,
  nextLabel,
  playLabel,
  pauseLabel,
  resumeHint,
  exitHint,
  disableStep,
  disablePlay,
  onPrevious,
  onNext,
  onTogglePlay,
  onHoverChange,
}) => {
  const resumeSeen = useRef(false);
  const [resumeHintOn, setResumeHintOn] = useState(false);
  const [exitTipOn, setExitTipOn] = useState(false);
  const controlsClassName = visible
    ? 'pointer-events-auto opacity-100'
    : 'pointer-events-none opacity-0';

  useEffect(() => {
    if (!paused || !visible || resumeSeen.current) {
      if (!paused || !visible) setResumeHintOn(false);
      return undefined;
    }
    setResumeHintOn(true);
    const timer = window.setTimeout(() => {
      resumeSeen.current = true;
      setResumeHintOn(false);
    }, CAROUSEL_FULLSCREEN_RESUME_HINT_MS);
    return () => window.clearTimeout(timer);
  }, [paused, visible]);

  useEffect(() => {
    let storage: Storage | null = null;
    try {
      storage = window.sessionStorage;
    } catch {
      storage = null;
    }
    if (readFullscreenExitTipSeen(storage)) return undefined;
    markFullscreenExitTipSeen(storage);
    setExitTipOn(true);
    const timer = window.setTimeout(() => setExitTipOn(false), CAROUSEL_FULLSCREEN_EXIT_TIP_MS);
    return () => window.clearTimeout(timer);
  }, []);

  const buttons = [
    {
      key: 'previous',
      label: previousLabel,
      disabled: disableStep,
      onClick: onPrevious,
      icon: <LeftOutlined style={{ fontSize: 14 }} />,
    },
    {
      key: 'toggle',
      label: paused ? playLabel : pauseLabel,
      disabled: disablePlay,
      onClick: onTogglePlay,
      icon: paused
        ? <CaretRightOutlined style={{ fontSize: 14 }} />
        : <PauseOutlined style={{ fontSize: 14 }} />,
    },
    {
      key: 'next',
      label: nextLabel,
      disabled: disableStep,
      onClick: onNext,
      icon: <RightOutlined style={{ fontSize: 14 }} />,
    },
  ];

  return (
    <div className="pointer-events-none absolute inset-0 z-20" style={chromeVars}>
      {exitTipOn ? (
        <div
          className={`absolute bottom-[16px] left-[16px] ${hintClassName}`}
          data-testid="carousel-fullscreen-exit-hint"
        >
          {exitHint}
        </div>
      ) : null}
      <div
        className="pointer-events-auto absolute bottom-[16px] right-[16px] h-[80px] w-[120px] cursor-auto"
        data-testid="carousel-fullscreen-hotzone"
        onMouseEnter={() => onHoverChange(true)}
        onMouseMove={() => {
          if (!visible) onHoverChange(true);
        }}
        onMouseLeave={() => onHoverChange(false)}
      >
        {resumeHintOn ? (
          <div
            className={`absolute right-0 bottom-11 whitespace-nowrap ${hintClassName}`}
            data-testid="carousel-fullscreen-resume-hint"
          >
            {resumeHint}
          </div>
        ) : null}
        <div
          className={`absolute right-0 bottom-0 flex h-[40px] items-center gap-1 rounded-[10px] border border-(--carousel-fs-border) bg-(--carousel-fs-surface) px-1.5 backdrop-blur-[12px] transition-opacity duration-300 ${controlsClassName}`}
          data-testid="carousel-fullscreen-controls"
          aria-hidden={!visible}
        >
          {buttons.map((button) => (
            <button
              key={button.key}
              type="button"
              className={`${ghostButtonClassName} h-[28px] w-[28px]`}
              aria-label={button.label}
              tabIndex={visible ? 0 : -1}
              disabled={button.disabled}
              onClick={button.onClick}
            >
              {button.icon}
            </button>
          ))}
        </div>
      </div>
      <CarouselFullscreenProgress
        slides={slides}
        index={index}
        paused={paused}
        remainingMs={remainingMs}
        remainingClock={remainingClock}
      />
    </div>
  );
};

export default CarouselFullscreenChrome;
