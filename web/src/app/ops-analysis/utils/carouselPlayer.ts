export const CAROUSEL_DWELL_MIN_SECONDS = 5;
export const CAROUSEL_DWELL_MAX_SECONDS = 300;
export const CAROUSEL_DEFAULT_DWELL_SECONDS = 30;
export const CAROUSEL_MAX_ITEMS = 50;
/** 本轮全部不可用时，隔这段时间再开一轮，避免空转刷接口。 */
export const CAROUSEL_UNAVAILABLE_RETRY_MS = 10_000;

export interface CarouselSlideInput {
  key: string;
  available: boolean;
  dwellSeconds: number;
}

export interface CarouselPlayerState {
  slides: CarouselSlideInput[];
  index: number;
  paused: boolean;
  remainingMs: number;
  visit: number;
  /** 全部不可用时的重试倒计时。为 0 表示没有等待。 */
  holdMs: number;
}

export type CarouselPlayerAction =
  | { type: 'reset'; slides: CarouselSlideInput[]; preferKey?: string | null; retainUnavailable?: boolean }
  | { type: 'tick'; deltaMs: number }
  | { type: 'next' }
  | { type: 'prev' }
  | { type: 'togglePause' }
  | { type: 'setPaused'; paused: boolean }
  | { type: 'selectIndex'; index: number }
  | { type: 'syncSlides'; slides: CarouselSlideInput[] }
  | { type: 'markUnavailable'; key: string };

export const clampCarouselDwellSeconds = (
  value: unknown,
  fallback = CAROUSEL_DEFAULT_DWELL_SECONDS,
): number => {
  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(
    CAROUSEL_DWELL_MAX_SECONDS,
    Math.max(CAROUSEL_DWELL_MIN_SECONDS, Math.round(parsed)),
  );
};

export const carouselHiddenGroupIds = (
  canvasGroupIds: readonly number[],
  carouselGroupIds: readonly number[],
): number[] => {
  const visible = new Set(canvasGroupIds);
  return carouselGroupIds.filter((groupId) => !visible.has(groupId));
};

const dwellMs = (slide: CarouselSlideInput | undefined): number =>
  Math.max(1, (slide?.dwellSeconds ?? CAROUSEL_DEFAULT_DWELL_SECONDS) * 1000);

export const stepCarouselIndex = (
  slides: readonly CarouselSlideInput[],
  index: number,
  direction: 1 | -1,
): number => {
  const available = slides.flatMap((slide, slideIndex) => (slide.available ? [slideIndex] : []));
  if (available.length === 0) {
    return -1;
  }
  if (index < 0 || !slides[index]?.available) {
    if (direction > 0) {
      return available.find((slideIndex) => slideIndex > index) ?? available[0];
    }
    return [...available].reverse().find((slideIndex) => slideIndex < index) ?? available[available.length - 1];
  }
  const position = available.indexOf(index);
  const next = (position + direction + available.length) % available.length;
  return available[next];
};

const withIndex = (
  state: CarouselPlayerState,
  slides: CarouselSlideInput[],
  index: number,
  visit: number,
): CarouselPlayerState => ({
  slides,
  index,
  paused: state.paused,
  remainingMs: index < 0 ? 0 : dwellMs(slides[index]),
  visit,
  holdMs: 0,
});

const restoreSkippedSlides = (slides: readonly CarouselSlideInput[]): CarouselSlideInput[] => {
  if (slides.every((slide) => slide.available)) {
    return slides as CarouselSlideInput[];
  }
  return slides.map((slide) => (slide.available ? slide : { ...slide, available: true }));
};

const holdUntilRetry = (
  state: CarouselPlayerState,
  slides: CarouselSlideInput[],
): CarouselPlayerState => ({
  slides,
  index: -1,
  paused: state.paused,
  remainingMs: 0,
  visit: state.visit,
  holdMs: CAROUSEL_UNAVAILABLE_RETRY_MS,
});

const resumeAfterHold = (state: CarouselPlayerState): CarouselPlayerState => {
  const slides = restoreSkippedSlides(state.slides);
  return withIndex(state, slides, stepCarouselIndex(slides, -1, 1), state.visit + 1);
};

const advanceCarousel = (
  state: CarouselPlayerState,
  direction: 1 | -1,
): CarouselPlayerState => {
  const upcoming = stepCarouselIndex(state.slides, state.index, direction);
  const opensNextLap = direction > 0
    && upcoming >= 0
    && upcoming <= state.index
    && state.slides.some((slide) => !slide.available);
  if (opensNextLap) {
    const slides = restoreSkippedSlides(state.slides);
    const index = stepCarouselIndex(slides, state.index, 1);
    if (index < 0) {
      return holdUntilRetry(state, slides);
    }
    return withIndex(state, slides, index, state.visit + 1);
  }
  if (upcoming < 0) {
    return holdUntilRetry(state, state.slides);
  }
  return withIndex(state, state.slides, upcoming, state.visit + 1);
};

export const createCarouselPlayerState = (
  slides: CarouselSlideInput[],
  preferKey?: string | null,
): CarouselPlayerState => {
  const preferred = preferKey ? slides.findIndex((slide) => slide.key === preferKey && slide.available) : -1;
  const index = preferred >= 0 ? preferred : stepCarouselIndex(slides, -1, 1);
  return {
    slides,
    index,
    paused: false,
    remainingMs: index < 0 ? 0 : dwellMs(slides[index]),
    visit: 0,
    holdMs: index < 0 && slides.length > 0 ? CAROUSEL_UNAVAILABLE_RETRY_MS : 0,
  };
};

const carouselErrorStatus = (error: unknown): number => {
  if (typeof error !== 'object' || error === null || !('status' in error)) {
    return Number.NaN;
  }
  return Number((error as { status?: unknown }).status);
};

export const isCarouselBusinessFailure = (error: unknown): boolean => {
  const status = carouselErrorStatus(error);
  return status === 403 || status === 404;
};

/** 401 交给全局会话过期处理，不记入本轮跳过。 */
export const isCarouselSessionFailure = (error: unknown): boolean => carouselErrorStatus(error) === 401;

/** 预取的瞬时失败留到切入再试；403/404 以及切入仍失败只跳过本轮。 */
export const reduceCarouselLoad = (
  state: CarouselPlayerState,
  event: { key: string; phase: 'prefetch' | 'enter'; ok: boolean; business?: boolean },
): CarouselPlayerState => {
  if (event.ok || (event.phase === 'prefetch' && !event.business)) {
    return state;
  }
  return reduceCarouselPlayer(state, { type: 'markUnavailable', key: event.key });
};

export const reduceCarouselPlayer = (
  state: CarouselPlayerState,
  action: CarouselPlayerAction,
): CarouselPlayerState => {
  switch (action.type) {
    case 'reset': {
      const next = createCarouselPlayerState(action.slides, action.preferKey);
      const retained = action.retainUnavailable && action.preferKey
        ? action.slides.findIndex((slide) => slide.key === action.preferKey)
        : -1;
      const index = retained >= 0 ? retained : next.index;
      const kept = Boolean(action.preferKey) && action.slides[index]?.key === action.preferKey;
      return {
        ...next,
        index,
        remainingMs: index < 0 ? 0 : dwellMs(action.slides[index]),
        paused: state.paused,
        visit: kept || state.slides.length === 0 ? state.visit : state.visit + 1,
      };
    }
    case 'togglePause':
      if (state.index < 0 && state.holdMs <= 0) {
        return state;
      }
      return { ...state, paused: !state.paused };
    case 'setPaused':
      if (state.paused === action.paused) {
        return state;
      }
      return { ...state, paused: action.paused };
    case 'selectIndex':
      if (action.index < 0 || action.index >= state.slides.length || action.index === state.index) {
        return state;
      }
      return withIndex(state, state.slides, action.index, state.visit + 1);
    case 'syncSlides': {
      const current = state.index >= 0 ? state.slides[state.index] : undefined;
      if (!current) {
        return { ...state, slides: action.slides };
      }
      const index = action.slides.findIndex((slide) => slide.key === current.key);
      if (index < 0) {
        return state;
      }
      const next = action.slides[index];
      const remainingMs = next.dwellSeconds === current.dwellSeconds
        ? state.remainingMs
        : Math.max(0, state.remainingMs + (next.dwellSeconds - current.dwellSeconds) * 1000);
      return { ...state, slides: action.slides, index, remainingMs };
    }
    case 'tick': {
      if (state.paused) {
        return state;
      }
      if (state.index >= 0 && state.slides[state.index] && !state.slides[state.index].available) {
        return advanceCarousel(state, 1);
      }
      if (state.holdMs > 0) {
        const holdMs = state.holdMs - Math.max(0, action.deltaMs);
        if (holdMs > 0) {
          return { ...state, holdMs };
        }
        return resumeAfterHold(state);
      }
      if (state.index < 0) {
        return state;
      }
      const remainingMs = state.remainingMs - Math.max(0, action.deltaMs);
      if (remainingMs > 0) {
        return { ...state, remainingMs };
      }
      return advanceCarousel(state, 1);
    }
    case 'next':
    case 'prev':
      if (state.index < 0) {
        return state;
      }
      return advanceCarousel(state, action.type === 'next' ? 1 : -1);
    case 'markUnavailable': {
      const target = state.slides.find((slide) => slide.key === action.key);
      if (!target?.available) {
        return state;
      }
      const slides = state.slides.map((slide) => (
        slide.key === action.key ? { ...slide, available: false } : slide
      ));
      const current = state.slides[state.index];
      if (!current || current.key !== action.key) {
        return { ...state, slides };
      }
      const index = stepCarouselIndex(slides, state.index, 1);
      if (index < 0) {
        return holdUntilRetry(state, slides);
      }
      return withIndex(state, slides, index, state.visit + 1);
    }
    default:
      return state;
  }
};

export const skippedCarouselCount = (state: CarouselPlayerState): number =>
  state.slides.filter((slide) => !slide.available).length;

export const isCarouselHotkeyBlocked = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    return true;
  }
  if (target.isContentEditable) {
    return true;
  }
  return Boolean(target.closest('[role="listbox"], [role="combobox"], .ant-select, .ant-picker, .ant-modal'));
};

export const isCarouselOverlayOpen = (): boolean => {
  if (typeof document === 'undefined') {
    return false;
  }
  return Boolean(document.querySelector(
    '.ant-select-dropdown:not(.ant-select-dropdown-hidden), .ant-picker-dropdown:not(.ant-picker-dropdown-hidden)',
  ));
};
