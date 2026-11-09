export interface CarouselRemainingClock {
  subscribe: (onStoreChange: () => void) => () => void;
  getSnapshot: () => number;
}

export interface CarouselRemainingClockStore extends CarouselRemainingClock {
  set: (remainingMs: number) => void;
}

/** 播放倒计时放在 React 状态之外，进度条自己订阅，画布树不跟 250ms tick 走。 */
export const createCarouselRemainingClock = (
  initialMs: number,
): CarouselRemainingClockStore => {
  let remainingMs = initialMs;
  const listeners = new Set<() => void>();
  return {
    subscribe(onStoreChange) {
      listeners.add(onStoreChange);
      return () => {
        listeners.delete(onStoreChange);
      };
    },
    getSnapshot() {
      return remainingMs;
    },
    set(next) {
      if (Object.is(remainingMs, next)) {
        return;
      }
      remainingMs = next;
      listeners.forEach((listener) => listener());
    },
  };
};
