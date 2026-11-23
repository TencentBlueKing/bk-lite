import axios from 'axios';

/**
 * Browser cancellation of an in-flight request.
 * Timeout (ECONNABORTED) and network loss (ERR_NETWORK) are not cancellation.
 */
export const isTransportCanceled = (error: unknown): boolean => {
  if (!error || typeof error !== 'object') return false;
  if (axios.isCancel(error)) return true;
  const named = error as { name?: string; code?: string };
  return named.code === 'ERR_CANCELED'
    || named.name === 'CanceledError'
    || named.name === 'AbortError';
};

export const createTransportCancelError = (): Error & { code: string } => {
  const error = new Error('canceled') as Error & { code: string };
  error.name = 'CanceledError';
  error.code = 'ERR_CANCELED';
  return error;
};

interface DelayAbortSignal {
  readonly aborted: boolean;
  addEventListener?: (
    type: 'abort',
    listener: () => void,
    options?: { once?: boolean },
  ) => void;
  removeEventListener?: (type: 'abort', listener: () => void) => void;
}

/** Resolve after delayMs, or reject when signal aborts. No signal keeps the plain timer. */
export const waitUntilDelayOrAbort = (
  delayMs: number,
  signal?: DelayAbortSignal,
): Promise<void> => {
  if (!signal) {
    return new Promise((resolve) => {
      setTimeout(resolve, delayMs);
    });
  }
  if (signal.aborted) {
    return Promise.reject(createTransportCancelError());
  }
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer);
      signal.removeEventListener?.('abort', onAbort);
      reject(createTransportCancelError());
    };
    const timer = setTimeout(() => {
      signal.removeEventListener?.('abort', onAbort);
      resolve();
    }, delayMs);
    signal.addEventListener?.('abort', onAbort, { once: true });
  });
};
