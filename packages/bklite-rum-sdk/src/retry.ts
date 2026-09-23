export interface RetryOptions {
  fetch?: typeof fetch;
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
  random?: () => number;
  sleep?: (delayMs: number) => Promise<void>;
}

export class TransportRequestError extends Error {
  constructor(
    message: string,
    readonly retryable: boolean,
    readonly status?: number,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = 'TransportRequestError';
  }
}

const defaultSleep = (delayMs: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, delayMs);
  });

function retryAfterMs(
  response: Response,
  now = Date.now(),
): number | undefined {
  const value = response.headers.get('retry-after');
  if (!value) return undefined;

  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return seconds * 1000;
  }

  const timestamp = Date.parse(value);
  if (Number.isFinite(timestamp)) {
    return Math.max(0, timestamp - now);
  }

  return undefined;
}

async function drainResponse(response: Response): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) return;
  try {
    for (;;) {
      const { done } = await reader.read();
      if (done) return;
    }
  } finally {
    reader.releaseLock();
  }
}

const MAX_TIMER_DELAY_MS = 2_147_483_647;

export async function requestWithRetry(
  url: string,
  request: RequestInit,
  options: RetryOptions = {},
): Promise<Response> {
  const fetcher = options.fetch ?? globalThis.fetch;
  if (!fetcher) {
    throw new TransportRequestError('fetch is not available', false);
  }

  const maxRetries = Math.max(0, options.maxRetries ?? 3);
  const baseDelayMs = Math.max(0, options.baseDelayMs ?? 500);
  const maxDelayMs = Math.max(baseDelayMs, options.maxDelayMs ?? 30_000);
  const sleep = options.sleep ?? defaultSleep;
  const random = options.random ?? Math.random;
  const retryableStatuses = new Set([408, 429, 502, 503, 504]);
  let lastError: unknown;
  let currentRequest = request;

  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    let response: Response;
    try {
      response = await fetcher(url, currentRequest);
      if (response.status === 202) {
        await drainResponse(response);
        return response;
      }
    } catch (error) {
      lastError = error;
      if (currentRequest.keepalive === true) {
        currentRequest = { ...currentRequest, keepalive: false };
      }
      if (attempt < maxRetries) {
        const exponential = Math.min(maxDelayMs, baseDelayMs * 2 ** attempt);
        await sleep(Math.round(exponential * (0.5 + random() * 0.5)));
        continue;
      }
      break;
    }

    const retryable = retryableStatuses.has(response.status);
    if (!retryable || attempt >= maxRetries) {
      void response.body?.cancel();
      throw new TransportRequestError(
        `Core RUM transport request failed with status ${response.status}`,
        retryable,
        response.status,
      );
    }

    const delay = retryAfterMs(response);
    void response.body?.cancel();
    const exponential = Math.min(maxDelayMs, baseDelayMs * 2 ** attempt);
    await sleep(
      delay === undefined
        ? Math.round(exponential * (0.5 + random() * 0.5))
        : Math.min(delay, MAX_TIMER_DELAY_MS),
    );
  }

  throw new TransportRequestError(
    'Core RUM transport request failed',
    true,
    undefined,
    {
      cause: lastError,
    },
  );
}
