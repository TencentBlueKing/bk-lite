import {
  DEFAULT_SCROLL_SECONDS,
  readChartDisplay,
  type ChartDisplaySource,
} from '@/app/ops-analysis/utils/chartDisplay';

export interface RowScrollRead {
  readonly autoScroll: true | undefined;
  readonly screenEnabled: boolean;
  /** Seconds for one rendered row. Absent uses the two-second default. */
  readonly scrollSeconds?: number;
}

const rowDurationMs = (seconds: number | undefined): number => {
  if (typeof seconds === 'number' && Number.isFinite(seconds) && seconds > 0) {
    return seconds * 1000;
  }
  return DEFAULT_SCROLL_SECONDS * 1000;
};

export function rowScrollRead(
  source: ChartDisplaySource | undefined,
  screenEnabled: boolean,
): RowScrollRead {
  const display = readChartDisplay(source);
  return {
    autoScroll: display.autoScroll,
    screenEnabled,
    scrollSeconds: display.scrollSeconds,
  };
}

const rowPitch = (viewport: HTMLElement, rowSelector: string): number => {
  const rows = viewport.querySelectorAll(rowSelector);
  const first = rows[0] as HTMLElement | undefined;
  if (!first) return 0;
  for (let index = 1; index < rows.length; index += 1) {
    const next = rows[index] as HTMLElement;
    const delta = next.offsetTop - first.offsetTop;
    if (delta > 0) return delta;
  }
  return first.offsetHeight;
};

/**
 * The element that actually overflows. Prefer one that already scrolls.
 * The first match is the fallback while layout is still settling.
 */
export function findScrollViewport(
  root: ParentNode | null,
  selectors: readonly string[],
): HTMLElement | null {
  if (!root) return null;
  const nodes = selectors
    .map((selector) => root.querySelector(selector))
    .filter((node): node is HTMLElement => {
      if (!node || typeof node !== 'object') return false;
      const candidate = node as HTMLElement;
      return typeof candidate.scrollHeight === 'number' && typeof candidate.clientHeight === 'number';
    });
  return nodes.find((node) => node.scrollHeight - node.clientHeight > 1) ?? nodes[0] ?? null;
}

/**
 * Start the player on one viewport. Returns a disposer that stops the frame
 * and the hover listeners. Two widgets never share a frame or a scroll offset.
 * `pauseTarget` is the whole widget face (header, body, pagination). The offset
 * stays a float so a browser that drops fractions of scrollTop cannot stall.
 * The frame runs only while the fetched rows overflow.
 */
export function startRowAutoScroll(
  viewport: HTMLElement,
  read: () => RowScrollRead,
  rowSelector: string,
  pauseTarget: HTMLElement = viewport,
): () => void {
  const first = read();
  if (!(first.autoScroll === true && first.screenEnabled === true)) {
    return () => undefined;
  }

  let hovering = false;
  const onEnter = () => {
    hovering = true;
  };
  const onLeave = () => {
    hovering = false;
  };
  pauseTarget.addEventListener('pointerenter', onEnter);
  pauseTarget.addEventListener('pointerleave', onLeave);

  let started = false;
  let lastTime = 0;
  let frame = 0;
  let running = false;
  let position = viewport.scrollTop;
  let pitch = 0;
  let maxScroll = 0;
  let measuredAt = 0;

  const measure = (now: number) => {
    if (pitch > 0 && now - measuredAt < 500) return;
    measuredAt = now;
    const nextPitch = rowPitch(viewport, rowSelector);
    if (nextPitch > 0) pitch = nextPitch;
    maxScroll = viewport.scrollHeight - viewport.clientHeight;
  };

  const stopLoop = () => {
    running = false;
    cancelAnimationFrame(frame);
  };

  const step = (now: number) => {
    if (!running) return;
    const elapsed = started ? now - lastTime : 0;
    started = true;
    lastTime = now;
    const current = read();
    const paused = current.screenEnabled !== true || hovering;
    if (paused) {
      if (hovering && Math.abs(viewport.scrollTop - position) > 1) {
        position = viewport.scrollTop;
      }
    } else if (elapsed > 0) {
      measure(now);
      if (pitch <= 0 || maxScroll <= 0) {
        stopLoop();
        return;
      }
      position += (pitch * elapsed) / rowDurationMs(current.scrollSeconds);
      if (position >= maxScroll) position = 0;
      viewport.scrollTop = position;
    }
    frame = requestAnimationFrame(step);
  };

  const startLoop = () => {
    if (running) return;
    measure(0);
    if (pitch <= 0 || maxScroll <= 0) return;
    running = true;
    started = false;
    frame = requestAnimationFrame(step);
  };

  let observer: { disconnect: () => void } | undefined;
  if (typeof ResizeObserver === 'function' && typeof Element !== 'undefined' && viewport instanceof Element) {
    const watched = new ResizeObserver(() => {
      measuredAt = 0;
      pitch = 0;
      if (running) return;
      startLoop();
    });
    watched.observe(viewport);
    const content = viewport.firstElementChild;
    if (content instanceof Element) watched.observe(content);
    observer = watched;
  }

  startLoop();

  return () => {
    stopLoop();
    observer?.disconnect();
    pauseTarget.removeEventListener('pointerenter', onEnter);
    pauseTarget.removeEventListener('pointerleave', onLeave);
  };
}

const TABLE_VIEWPORT_SELECTORS = ['.ant-table-body', '.ant-table-content'] as const;

/** Bind the table player to the scrolling body, and pause on the whole slot. */
export function watchTableAutoScroll(
  slot: HTMLElement | null,
  read: () => RowScrollRead,
): () => void {
  let stop = () => undefined;
  let frame = 0;
  let attempts = 0;
  let cancelled = false;
  const bind = () => {
    if (cancelled) return;
    const viewport = findScrollViewport(slot, TABLE_VIEWPORT_SELECTORS);
    if (viewport) {
      stop = startRowAutoScroll(
        viewport,
        read,
        '.ant-table-tbody .ant-table-row',
        slot ?? viewport,
      );
      return;
    }
    attempts += 1;
    if (attempts < 30) frame = requestAnimationFrame(bind);
  };
  bind();
  return () => {
    cancelled = true;
    cancelAnimationFrame(frame);
    stop();
  };
}
