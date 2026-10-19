export const LINE_DATA_LINK_CLICK_DELAY_MS = 250;
export const RIGHT_CLICK_DRAG_THRESHOLD_PX = 6;

interface TimerPort {
  set: (callback: () => void, ms: number) => number;
  clear: (id: number) => void;
}

const browserTimers = (): TimerPort => ({
  set: (callback, ms) => window.setTimeout(callback, ms) as unknown as number,
  clear: (id) => window.clearTimeout(id),
});

/** 单击延迟触发；dblclick 或 dataZoom 调用 cancel 后，同一轮事件里的单击不再打开链接。 */
export const createDelayedClickScheduler = (
  delayMs = LINE_DATA_LINK_CLICK_DELAY_MS,
  timers: TimerPort = browserTimers(),
) => {
  let timer: number | null = null;
  let blocked = false;
  return {
    schedule(run: () => void) {
      if (blocked) return;
      if (timer != null) timers.clear(timer);
      timer = timers.set(() => {
        timer = null;
        run();
      }, delayMs);
    },
    cancel() {
      blocked = true;
      if (timer != null) {
        timers.clear(timer);
        timer = null;
      }
      timers.set(() => {
        blocked = false;
      }, 0);
    },
    dispose() {
      if (timer != null) {
        timers.clear(timer);
        timer = null;
      }
    },
  };
};

export const createRightClickGesture = (
  thresholdPx = RIGHT_CLICK_DRAG_THRESHOLD_PX,
) => {
  let start: { x: number; y: number } | null = null;
  return {
    pointerDown(event: { button?: number; clientX: number; clientY: number }) {
      if (event.button !== 2) return;
      start = { x: event.clientX, y: event.clientY };
    },
    decide(event: { clientX: number; clientY: number }, hit: boolean) {
      const origin = start;
      start = null;
      const displacement = origin
        ? Math.hypot(event.clientX - origin.x, event.clientY - origin.y)
        : Number.POSITIVE_INFINITY;
      const open = hit && displacement < thresholdPx;
      return {
        open,
        dragged: displacement >= thresholdPx,
        stopImmediatePropagation: open,
      };
    },
  };
};

/** 与 ECharts 雷达默认一致：startAngle 90°，逆时针。 */
export const nearestRadarIndicatorIndex = (
  point: { x: number; y: number },
  center: { x: number; y: number },
  count: number,
  options?: { startAngle?: number; clockwise?: boolean },
): number | undefined => {
  if (!Number.isFinite(count) || count <= 0) return undefined;
  if (count === 1) return 0;
  const dx = point.x - center.x;
  const dy = point.y - center.y;
  if (dx === 0 && dy === 0) return 0;
  const clickAngle = Math.atan2(-dy, dx);
  const start = ((options?.startAngle ?? 90) * Math.PI) / 180;
  const sign = options?.clockwise ? -1 : 1;
  const step = (Math.PI * 2) / count;
  let best = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < count; index += 1) {
    const raw = start + sign * index * step;
    const angle = Math.atan2(Math.sin(raw), Math.cos(raw));
    const delta = Math.atan2(
      Math.sin(clickAngle - angle),
      Math.cos(clickAngle - angle),
    );
    const distance = Math.abs(delta);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = index;
    }
  }
  return best;
};

export interface RadarClickGeometry {
  centerX: number;
  centerY: number;
  indicatorCount: number;
  startAngle?: number;
  clockwise?: boolean;
}

export const readRadarClickGeometry = (
  chart: unknown,
  indicatorCount: number,
): RadarClickGeometry | undefined => {
  if (indicatorCount <= 0) return undefined;
  const view = chart as {
    getWidth?: () => number;
    getHeight?: () => number;
    getModel?: () => {
      getComponent?: (
        type: string,
        index: number,
      ) => { coordinateSystem?: { cx?: number; cy?: number } } | undefined;
    };
  } | null | undefined;
  const coord = view?.getModel?.()?.getComponent?.('radar', 0)?.coordinateSystem;
  const width = view?.getWidth?.() ?? 0;
  const height = view?.getHeight?.() ?? 0;
  const centerX = typeof coord?.cx === 'number' ? coord.cx : width / 2;
  const centerY = typeof coord?.cy === 'number' ? coord.cy : height / 2;
  if (!Number.isFinite(centerX) || !Number.isFinite(centerY)) return undefined;
  return { centerX, centerY, indicatorCount };
};

/** 只有查看态、并且这条数据链接真的会跳转时，才关掉扇区选中。 */
export const pieSectorSelectedMode = (
  surface: 'edit' | 'view' | 'share',
  kind?: string,
): false | 'single' => (
  surface === 'view' && kind === 'data' ? false : 'single'
);

export const openPreparedInteractionNavigation = (
  prepared: { href: string; mode: 'sameFrame' | 'newTab' },
  target: {
    open: (url: string, targetName: string, features: string) => void;
    location: { href: string };
  },
) => {
  if (prepared.mode === 'newTab') {
    target.open(prepared.href, '_blank', 'noopener,noreferrer');
    return;
  }
  target.location.href = prepared.href;
};
