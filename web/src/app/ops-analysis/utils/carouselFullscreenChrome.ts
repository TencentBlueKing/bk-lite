/** 全屏叠层盖在任意画布上，颜色固定，不跟控制台主题走。 */
export const CAROUSEL_FULLSCREEN_CHROME = {
  surface: 'rgba(6, 16, 32, 0.78)',
  border: 'rgba(103, 232, 249, 0.55)',
  ink: '#e0f2fe',
  hover: 'rgba(103, 232, 249, 0.16)',
  track: 'rgba(255, 255, 255, 0.16)',
  played: 'rgba(224, 242, 254, 0.92)',
  upcoming: 'rgba(255, 255, 255, 0.18)',
  current: '#22d3ee',
  paused: '#FAAD14',
} as const;

/** 指针离开右下热区后，未暂停时三键簇再停留这段时间。 */
export const CAROUSEL_FULLSCREEN_CONTROLS_IDLE_MS = 500;
/** 暂停后热区内「空格继续」只亮一次，到点收起。 */
export const CAROUSEL_FULLSCREEN_RESUME_HINT_MS = 2000;
/** 每次浏览器标签第一次进入全屏时，「Esc 退出」亮这段时间。 */
export const CAROUSEL_FULLSCREEN_EXIT_TIP_MS = 2500;
export const CAROUSEL_FULLSCREEN_EXIT_TIP_KEY = 'ops-carousel-fullscreen-exit-tip';
/** 画布数不超过这个值时进度条分段，再多就合成一条。 */
export const CAROUSEL_FULLSCREEN_SEGMENT_MAX = 20;

export type FullscreenChromeEvent =
  | 'hotzone-enter'
  | 'hotzone-leave'
  | 'hide-elapsed'
  | 'paused'
  | 'resumed';

export interface FullscreenChromePlan {
  visible: boolean;
  armIdleTimer: boolean;
}

export interface FullscreenSlideProgressInput {
  available: boolean;
  dwellSeconds: number;
}

export type FullscreenSegmentTone = 'played' | 'current' | 'upcoming' | 'unavailable';

export interface FullscreenSegment {
  tone: FullscreenSegmentTone;
  /** 0–1。已播为 1，当前段为已消耗停留占比，其余为 0。 */
  fill: number;
}

export interface FullscreenProgressModel {
  mode: 'segments' | 'continuous';
  segments: FullscreenSegment[];
  /** 按序号加当前段进度，范围 0–1。 */
  continuous: number;
  currentColor: string;
}

const clampUnit = (value: number): number => {
  if (!Number.isFinite(value)) return 0;
  return Math.min(1, Math.max(0, value));
};

/**
 * 右下热区唤出三键簇。
 * 进入热区或暂停时钉住；离开热区且未暂停时先保持可见并启动短延迟；
 * 延迟结束或继续播放时，只有仍停在热区才留下。
 */
export const planFullscreenChrome = (
  event: FullscreenChromeEvent,
  flags: { paused: boolean; hoveringHotzone: boolean },
): FullscreenChromePlan => {
  const pinned = flags.paused || flags.hoveringHotzone;
  if (event === 'hotzone-enter' || event === 'paused') {
    return { visible: true, armIdleTimer: false };
  }
  if (event === 'hotzone-leave') {
    return { visible: true, armIdleTimer: !flags.paused };
  }
  return { visible: pinned, armIdleTimer: false };
};

/** 全屏轮播舞台始终显示系统光标。三键簇收起时也不隐藏。 */
export const fullscreenStageCursor = (): 'auto' => 'auto';

export const readFullscreenExitTipSeen = (
  storage: Pick<Storage, 'getItem'> | null,
): boolean => {
  if (!storage) return false;
  try {
    return storage.getItem(CAROUSEL_FULLSCREEN_EXIT_TIP_KEY) === '1';
  } catch {
    return false;
  }
};

export const markFullscreenExitTipSeen = (
  storage: Pick<Storage, 'setItem'> | null,
): void => {
  if (!storage) return;
  try {
    storage.setItem(CAROUSEL_FULLSCREEN_EXIT_TIP_KEY, '1');
  } catch {
    // 隐私模式写不进 sessionStorage 时，这次提示照样收起。
  }
};

export const carouselDwellFill = (dwellSeconds: number, remainingMs: number): number => {
  const dwellMs = Math.max(1, dwellSeconds) * 1000;
  return clampUnit((dwellMs - remainingMs) / dwellMs);
};

export const resolveCarouselFullscreenProgress = (input: {
  slides: readonly FullscreenSlideProgressInput[];
  index: number;
  remainingMs: number;
  paused: boolean;
}): FullscreenProgressModel => {
  const count = input.slides.length;
  const index = input.index < 0 || count === 0
    ? -1
    : Math.min(input.index, count - 1);
  const current = index >= 0 ? input.slides[index] : undefined;
  const currentFill = current?.available
    ? carouselDwellFill(current.dwellSeconds, input.remainingMs)
    : 0;
  const segments = input.slides.map((slide, slideIndex): FullscreenSegment => {
    if (!slide.available) return { tone: 'unavailable', fill: 0 };
    if (index < 0) return { tone: 'upcoming', fill: 0 };
    if (slideIndex < index) return { tone: 'played', fill: 1 };
    if (slideIndex === index) return { tone: 'current', fill: currentFill };
    return { tone: 'upcoming', fill: 0 };
  });
  const continuous = index < 0 || count === 0
    ? 0
    : clampUnit((index + currentFill) / count);
  return {
    mode: count > CAROUSEL_FULLSCREEN_SEGMENT_MAX ? 'continuous' : 'segments',
    segments,
    continuous,
    currentColor: input.paused
      ? CAROUSEL_FULLSCREEN_CHROME.paused
      : CAROUSEL_FULLSCREEN_CHROME.current,
  };
};
