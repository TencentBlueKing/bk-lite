import type { ReportFileDownload } from '@/app/opspilot/types/global';

const API_V1_PREFIX = '/api/v1/';
const API_PROXY_PREFIX = '/api/proxy/';

interface NormalizeDownloadUrlOptions {
  currentOrigin?: string;
  allowedOrigins?: string[];
}

const getCurrentOrigin = () => {
  if (typeof window === 'undefined') {
    return '';
  }
  return window.location.origin;
};

const normalizeOrigin = (origin?: string) => {
  const value = origin?.trim();
  if (!value) {
    return '';
  }

  try {
    return new URL(value).origin;
  } catch {
    return '';
  }
};

const getConfiguredAllowedOrigins = () => {
  const rawOrigins = process.env.NEXT_PUBLIC_OPSPILOT_DOWNLOAD_ORIGINS;
  if (!rawOrigins) {
    return [];
  }

  return rawOrigins
    .split(',')
    .map(normalizeOrigin)
    .filter(Boolean);
};

const getAllowedOrigins = (options?: NormalizeDownloadUrlOptions) => {
  return new Set([
    normalizeOrigin(options?.currentOrigin || getCurrentOrigin()),
    ...getConfiguredAllowedOrigins(),
    ...(options?.allowedOrigins || []).map(normalizeOrigin),
  ].filter(Boolean));
};

const hasUnsafeCharacters = (url: string) => /[\u0000-\u001F\u007F\\]/.test(url);
const hasAllowedAbsoluteScheme = (url: string) => /^(https?:\/\/|blob:)/i.test(url);

const normalizeApiProxyPath = (url: string) => {
  if (url.startsWith(API_V1_PREFIX)) {
    return `${API_PROXY_PREFIX}${url.slice(API_V1_PREFIX.length)}`;
  }

  return url;
};

const isSameOriginUrl = (url: URL, allowedOrigins: Set<string>) => {
  return allowedOrigins.size > 0 && allowedOrigins.has(url.origin);
};

export const normalizeSafeDownloadUrl = (
  url?: string,
  options?: NormalizeDownloadUrlOptions
): string => {
  const trimmedUrl = url?.trim();
  if (!trimmedUrl || hasUnsafeCharacters(trimmedUrl)) {
    return '';
  }

  const normalizedUrl = normalizeApiProxyPath(trimmedUrl);
  if (normalizedUrl.startsWith('/') && !normalizedUrl.startsWith('//')) {
    return normalizedUrl;
  }

  const allowedOrigins = getAllowedOrigins(options);
  try {
    if (!hasAllowedAbsoluteScheme(normalizedUrl)) {
      return '';
    }

    const parsedUrl = new URL(normalizedUrl, options?.currentOrigin || getCurrentOrigin() || undefined);
    if (parsedUrl.username || parsedUrl.password) {
      return '';
    }

    if (parsedUrl.protocol === 'blob:') {
      return isSameOriginUrl(parsedUrl, allowedOrigins) ? normalizedUrl : '';
    }

    if (
      (parsedUrl.protocol === 'https:' || parsedUrl.protocol === 'http:')
      && isSameOriginUrl(parsedUrl, allowedOrigins)
    ) {
      return normalizedUrl;
    }
  } catch {
    return '';
  }

  return '';
};

export const hydrateGeneratedFileLinks = (
  html: string,
  downloads?: ReportFileDownload[]
): string => {
  if (!html || !downloads?.length || typeof window === 'undefined') {
    return html;
  }

  const linkableDownloads = downloads
    .map(download => ({
      download,
      safeUrl: normalizeSafeDownloadUrl(download.file_url),
    }))
    .filter(item => item.safeUrl);
  if (linkableDownloads.length === 0 || !html.includes('<a')) {
    return html;
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  const anchors = Array.from(doc.querySelectorAll('a:not([href])'));
  if (anchors.length === 0) {
    return html;
  }

  const normalizeText = (value: string) => value.replace(/^下载/, '').replace(/\.[^.]+$/, '').trim().toLowerCase();

  anchors.forEach(anchor => {
    const anchorText = normalizeText(anchor.textContent || '');
    const matchedDownload = linkableDownloads.length === 1
      ? linkableDownloads[0]
      : linkableDownloads.find(({ download }) => {
        const fileName = normalizeText(download.filename);
        return anchorText && (fileName.includes(anchorText) || anchorText.includes(fileName));
      });

    if (!matchedDownload) {
      return;
    }

    anchor.setAttribute('href', matchedDownload.safeUrl);
    anchor.setAttribute('target', '_blank');
    anchor.setAttribute('rel', 'noopener noreferrer');
  });

  return doc.body.innerHTML;
};
