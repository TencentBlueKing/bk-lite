export const SSE_TIMEOUT_MS = 300_000;
export const DEFAULT_TIMEOUT_MS = 60_000;

export function getInitialProxyTimeoutMs(acceptHeader: string | null): number {
  const acceptsEventStream = (acceptHeader || '')
    .split(',')
    .some((mediaType) => mediaType.split(';', 1)[0].trim().toLowerCase() === 'text/event-stream');

  return acceptsEventStream ? SSE_TIMEOUT_MS : DEFAULT_TIMEOUT_MS;
}
