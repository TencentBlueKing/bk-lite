export interface FrameScheduler {
  schedule(callback: () => void): number;
  cancel(id: number): void;
}

export interface StreamingFrameBatcher {
  schedule(text: string): void;
  flush(): void;
  cancel(): void;
}

function createBrowserFrameScheduler(): FrameScheduler {
  if (typeof requestAnimationFrame === 'function') {
    return {
      schedule: (callback) => requestAnimationFrame(callback),
      cancel: (id) => cancelAnimationFrame(id),
    };
  }
  return {
    schedule: (callback) => setTimeout(callback, 16) as unknown as number,
    cancel: (id) => clearTimeout(id),
  };
}

/** Coalesce high-frequency streaming text into at most one commit per animation frame. */
export function createStreamingFrameBatcher(
  commit: (text: string) => void,
  scheduler: FrameScheduler = createBrowserFrameScheduler(),
  shouldBatch: () => boolean = () => true
): StreamingFrameBatcher {
  let pendingText: string | null = null;
  let frameId: number | null = null;

  const commitPending = () => {
    frameId = null;
    if (pendingText === null) return;
    const text = pendingText;
    pendingText = null;
    commit(text);
  };

  return {
    schedule(text) {
      if (!shouldBatch()) {
        if (frameId !== null) {
          scheduler.cancel(frameId);
          frameId = null;
        }
        pendingText = null;
        commit(text);
        return;
      }
      pendingText = text;
      if (frameId === null) {
        frameId = scheduler.schedule(commitPending);
      }
    },
    flush() {
      if (frameId !== null) {
        scheduler.cancel(frameId);
        frameId = null;
      }
      commitPending();
    },
    cancel() {
      if (frameId !== null) {
        scheduler.cancel(frameId);
        frameId = null;
      }
      pendingText = null;
    },
  };
}
