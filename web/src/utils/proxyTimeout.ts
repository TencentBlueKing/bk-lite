export const DEFAULT_TIMEOUT_MS = 60_000;
export const SSE_TIMEOUT_MS = 300_000;
export const PROXY_TIMEOUT_HEADER = 'x-bklite-proxy-timeout-ms';

function acceptsEventStream(acceptHeader: string | null): boolean {
  return (acceptHeader || '').split(',').some((entry) => {
    const [mediaType, ...parameters] = entry.split(';');
    if (mediaType.trim().toLowerCase() !== 'text/event-stream') return false;

    const qualityParameter = parameters.find(
      (parameter) => parameter.split('=', 1)[0].trim().toLowerCase() === 'q'
    );
    if (!qualityParameter) return true;

    const quality = Number(qualityParameter.slice(qualityParameter.indexOf('=') + 1).trim());
    return Number.isFinite(quality) && quality > 0;
  });
}

export function getProxyTimeoutHeaderValue(requestTimeoutMs?: number): string | null {
  if (requestTimeoutMs === 0) return String(SSE_TIMEOUT_MS);
  if (!requestTimeoutMs || requestTimeoutMs <= DEFAULT_TIMEOUT_MS) return null;
  return String(Math.min(Math.trunc(requestTimeoutMs), SSE_TIMEOUT_MS));
}

export function getInitialProxyTimeoutMs(
  acceptHeader: string | null,
  requestedTimeoutHeader: string | null = null
): number {
  if (acceptsEventStream(acceptHeader)) return SSE_TIMEOUT_MS;

  const requestedTimeoutMs = Number(requestedTimeoutHeader);
  if (!Number.isFinite(requestedTimeoutMs) || requestedTimeoutMs <= DEFAULT_TIMEOUT_MS) {
    return DEFAULT_TIMEOUT_MS;
  }
  return Math.min(Math.trunc(requestedTimeoutMs), SSE_TIMEOUT_MS);
}

export function consumeProxyTimeoutMs(headers: Headers): number {
  const requestedTimeoutHeader = headers.get(PROXY_TIMEOUT_HEADER);
  headers.delete(PROXY_TIMEOUT_HEADER);
  return getInitialProxyTimeoutMs(headers.get('accept'), requestedTimeoutHeader);
}

export function scheduleProxyAbort(controller: AbortController, timeoutMs: number): ReturnType<typeof setTimeout> {
  return setTimeout(() => controller.abort(), timeoutMs);
}
