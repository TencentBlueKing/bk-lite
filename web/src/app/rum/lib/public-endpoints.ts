const COLLECT_PATH = '/rum/v1/collect';
const REPLAY_PATH = '/rum/v1/replay';
const SDK_PATH = '/rum/bklite-rum-sdk.js';

export interface RumBrowserEndpoints {
  collectUrl: string;
  replayUrl: string;
  sdkCdnUrl: string;
};

function normalizeOrigin(value: string | undefined): string {
  const trimmed = (value || '').trim();
  if (!trimmed) return '';
  try {
    const url = new URL(trimmed);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return '';
    if (url.username || url.password || url.search || url.hash) return '';
    if (url.pathname !== '/' && url.pathname !== '') return '';
    return url.origin;
  } catch {
    return '';
  }
}

/** Browser ingest URLs share the console origin. RUM_PUBLIC_ORIGIN overrides that prefix. */
export function rumBrowserEndpoints(
  consoleOrigin: string,
  publicOrigin?: string,
): RumBrowserEndpoints {
  const origin = normalizeOrigin(publicOrigin) || normalizeOrigin(consoleOrigin);
  return {
    collectUrl: origin ? `${origin}${COLLECT_PATH}` : '',
    replayUrl: origin ? `${origin}${REPLAY_PATH}` : '',
    sdkCdnUrl: origin ? `${origin}${SDK_PATH}` : '',
  };
}
