/** Lightweight UA parsing for the sessions explorer. */

export type DeviceClass = 'mobile' | 'tablet' | 'desktop';

export function parseDevice(ua: string): DeviceClass {
  if (/iPad|Tablet|PlayBook/i.test(ua)) return 'tablet';
  if (/Mobile|Android|iPhone|iPod|Windows Phone/i.test(ua)) return 'mobile';
  return 'desktop';
}

export function parseBrowser(ua: string): string {
  if (/Edg\//i.test(ua)) return 'Edge';
  if (/OPR\/|Opera/i.test(ua)) return 'Opera';
  if (/Firefox\//i.test(ua)) return 'Firefox';
  if (/SamsungBrowser/i.test(ua)) return 'Samsung';
  if (/Chrome\//i.test(ua)) return 'Chrome';
  if (/Safari\//i.test(ua)) return 'Safari';
  if (/MSIE|Trident/i.test(ua)) return 'IE';
  return ua ? 'Unknown' : '—';
}

export function displayRoute(route: string | undefined | null): string {
  const value = (route || '').trim();
  if (!value) return '';
  try {
    if (value.startsWith('http://') || value.startsWith('https://')) {
      return new URL(value).pathname || '/';
    }
  } catch {
    /* keep raw */
  }
  return value;
}

export function formatDurationMs(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return '—';
  const totalSec = Math.round(ms / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  if (min < 60) return sec ? `${min}m ${sec}s` : `${min}m`;
  const hr = Math.floor(min / 60);
  const remMin = min % 60;
  return remMin ? `${hr}h ${remMin}m` : `${hr}h`;
}

export function truncateMiddle(value: string, max: number): string {
  if (value.length <= max) return value;
  return `${value.slice(0, Math.floor(max / 2))}…${value.slice(-Math.floor(max / 2) + 1)}`;
}

/** Map Django grant URLs (`/api/v1/rum/...`) onto the BK-Lite browser proxy. */
export function rewriteRumSegmentUrl(url: string): string {
  if (url.startsWith('/api/v1/rum/')) {
    return `/api/proxy${url.slice('/api/v1'.length)}`;
  }
  if (url.startsWith('/rum/')) {
    return `/api/proxy${url}`;
  }
  return url;
}
