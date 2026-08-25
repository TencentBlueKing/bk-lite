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

const ATTACHMENT_DOWNLOAD_HREF_PATTERN =
  '(?:file:\\/\\/)?(?:https?:\\/\\/[^\\s/]+)?\\/api\\/(?:proxy|v1)\\/opspilot\\/bot_mgmt\\/workflow_attachment\\/download\\/[^\\s)\\]>\'"]+';

const MARKDOWN_LINK_RE = /\[[^\]]*\]\s*\(\s*[^)]+\)/g;
const HTML_ANCHOR_RE = /<a\b([^>]*)>([\s\S]*?)<\/a>/gi;

const attachmentDownloadMentionRe = () =>
  new RegExp(
    `(?:\\[[^\\]]*\\]\\s*\\(\\s*${ATTACHMENT_DOWNLOAD_HREF_PATTERN}\\s*\\)|${ATTACHMENT_DOWNLOAD_HREF_PATTERN})`,
    'gi',
  );

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

export const looksLikeAttachmentDownloadUrl = (value?: string): boolean => {
  const trimmed = value?.trim();
  if (!trimmed) {
    return false;
  }
  return new RegExp(`^(?:${ATTACHMENT_DOWNLOAD_HREF_PATTERN})\\/?$`, 'i').test(trimmed);
};

export const looksLikeFakeDownloadHref = (value?: string): boolean => {
  const trimmed = value?.trim() || '';
  if (!trimmed) {
    return true;
  }
  if (/地址\s*[:：]/.test(trimmed)) {
    return true;
  }
  if (/\{token\}|加密token/i.test(trimmed)) {
    return true;
  }
  if (/^file:/i.test(trimmed)) {
    return true;
  }
  if (/\/api\/v1\/file-view/i.test(trimmed)) {
    return true;
  }
  return false;
};

export const isRenderableReportDownload = (download?: ReportFileDownload): boolean => {
  if (!download) {
    return false;
  }
  if (download.content_base64) {
    return true;
  }
  return Boolean(normalizeSafeDownloadUrl(download.file_url));
};

export const toAbsoluteDownloadHref = (
  url?: string,
  options?: NormalizeDownloadUrlOptions,
): string => {
  const safeUrl = normalizeSafeDownloadUrl(url, options);
  if (!safeUrl) {
    return '';
  }
  if (!safeUrl.startsWith('/') || safeUrl.startsWith('//')) {
    return safeUrl;
  }
  const origin = normalizeOrigin(options?.currentOrigin || getCurrentOrigin());
  return origin ? `${origin}${safeUrl}` : safeUrl;
};

const resolveLinkableDownloads = (
  downloads?: ReportFileDownload[],
  options?: NormalizeDownloadUrlOptions,
) => {
  return (downloads || [])
    .map(download => ({
      download,
      safeUrl: normalizeSafeDownloadUrl(download.file_url, options),
    }))
    .filter(item => item.safeUrl);
};

const buildFriendlyDownloadAnchor = (
  downloads?: ReportFileDownload[],
  options?: NormalizeDownloadUrlOptions,
): string => {
  const linkableDownloads = resolveLinkableDownloads(downloads, options);
  if (linkableDownloads.length === 0) {
    return '附件可在对话中下载';
  }
  return linkableDownloads
    .map(({ download, safeUrl }) => (
      `<a href="${escapeHtml(safeUrl)}" download="${escapeHtml(download.filename)}">下载 ${escapeHtml(download.filename)}</a>`
    ))
    .join(' ');
};

const shouldRewriteMarkdownLink = (text: string, href: string): boolean => {
  return /下载/.test(text) || looksLikeFakeDownloadHref(href) || looksLikeAttachmentDownloadUrl(href);
};

const rewriteBareAttachmentUrls = (markdown: string, replacement: string): string => {
  return markdown.replace(attachmentDownloadMentionRe(), (match, offset, source) => {
    const start = typeof offset === 'number' ? offset : 0;
    const before = String(source).slice(Math.max(0, start - 6), start);
    if (before.endsWith('href="') || before.endsWith("href='")) {
      return match;
    }
    return replacement;
  });
};

export const rewriteAttachmentDownloadMentions = (
  markdown: string,
  downloads?: ReportFileDownload[],
  options?: NormalizeDownloadUrlOptions,
): string => {
  if (!markdown) {
    return markdown;
  }

  const replacement = buildFriendlyDownloadAnchor(downloads, options);
  const withMarkdownLinks = markdown.replace(MARKDOWN_LINK_RE, (match) => {
    const parsed = match.match(/^\[([^\]]*)\]\s*\(\s*([^)]+)\)/);
    if (!parsed) {
      return match;
    }
    return shouldRewriteMarkdownLink(parsed[1], parsed[2]) ? replacement : match;
  });
  const withHtmlAnchors = withMarkdownLinks.replace(HTML_ANCHOR_RE, (full, attrs, text) => {
    const href = String(attrs).match(/href\s*=\s*["']([^"']*)["']/i)?.[1] || '';
    const plainText = String(text).replace(/<[^>]+>/g, '');
    return shouldRewriteMarkdownLink(plainText, href) ? replacement : full;
  });
  return rewriteBareAttachmentUrls(withHtmlAnchors, replacement);
};

export const hydrateGeneratedFileLinks = (
  html: string,
  downloads?: ReportFileDownload[]
): string => {
  if (!html || !downloads?.length || typeof window === 'undefined') {
    return html;
  }

  const linkableDownloads = resolveLinkableDownloads(downloads);
  if (linkableDownloads.length === 0 || !html.includes('<a')) {
    return html;
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  const anchors = Array.from(doc.querySelectorAll('a'));
  if (anchors.length === 0) {
    return html;
  }

  const normalizeText = (value: string) => value.replace(/^下载/, '').replace(/\.[^.]+$/, '').trim().toLowerCase();

  anchors.forEach(anchor => {
    const href = anchor.getAttribute('href') || '';
    const safeHref = normalizeSafeDownloadUrl(href);
    const textLooksLikeDownload = /下载/.test(anchor.textContent || '');
    const needsRewrite = !href || looksLikeFakeDownloadHref(href) || !safeHref;
    if (!needsRewrite && !looksLikeAttachmentDownloadUrl(anchor.textContent || '')) {
      return;
    }
    if (
      needsRewrite
      && !textLooksLikeDownload
      && !looksLikeFakeDownloadHref(href)
      && !looksLikeAttachmentDownloadUrl(href)
    ) {
      return;
    }

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
    anchor.setAttribute('download', matchedDownload.download.filename);
    anchor.setAttribute('rel', 'noopener noreferrer');
    if (
      !href
      || looksLikeFakeDownloadHref(href)
      || looksLikeAttachmentDownloadUrl(href)
      || looksLikeAttachmentDownloadUrl(anchor.textContent || '')
    ) {
      anchor.textContent = `下载 ${matchedDownload.download.filename}`;
    }
  });

  return doc.body.innerHTML;
};
