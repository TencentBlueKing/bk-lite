const API_V1_PREFIX = '/api/v1/';
const API_PROXY_PREFIX = '/api/proxy/';

export type SessionAttachmentFile = {
  id: string;
  filename: string;
  fileUrl: string;
  ext: string;
};

const hasUnsafeCharacters = (url: string) => Array.from(url).some((character) => {
  const codePoint = character.codePointAt(0) ?? 0;
  return codePoint <= 0x1F || codePoint === 0x7F || character === '\\';
});

const hasParentSegment = (url: string) => url.split(/[?#]/, 1)[0].split('/').some((part) => {
  try {
    return decodeURIComponent(part) === '..';
  } catch {
    return true;
  }
});

const currentPageOrigin = () => {
  if (typeof window === 'undefined' || !window.location) {
    return '';
  }
  return window.location.origin || '';
};

/** 只放行同源地址，或已知的 `/api/proxy/`（含 `/api/v1/` 改写）路径。 */
export function normalizeSafeDownloadUrl(url?: string, currentOrigin?: string): string {
  const trimmed = url?.trim() ?? '';
  if (!trimmed || hasUnsafeCharacters(trimmed) || trimmed.startsWith('//')) {
    return '';
  }

  const normalized = trimmed.startsWith(API_V1_PREFIX)
    ? `${API_PROXY_PREFIX}${trimmed.slice(API_V1_PREFIX.length)}`
    : trimmed;
  if (
    (normalized.startsWith(API_PROXY_PREFIX) || normalized === '/api/proxy')
    && !hasParentSegment(normalized)
  ) {
    return normalized;
  }

  const origin = (currentOrigin ?? currentPageOrigin()).trim();
  if (!origin || !/^(https?:\/\/|blob:)/i.test(normalized)) {
    return '';
  }

  try {
    const allowedOrigin = new URL(origin).origin;
    const parsed = new URL(normalized);
    if (parsed.username || parsed.password || parsed.origin !== allowedOrigin) {
      return '';
    }
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:' && parsed.protocol !== 'blob:') {
      return '';
    }
    return normalized;
  } catch {
    return '';
  }
}

/** 非白名单地址不创建链接、不导航。 */
export function openSafeDownload(
  file: Pick<SessionAttachmentFile, 'fileUrl' | 'filename'>,
  currentOrigin?: string,
): boolean {
  const safeUrl = normalizeSafeDownloadUrl(file.fileUrl, currentOrigin);
  if (!safeUrl || typeof document === 'undefined' || !document.body) {
    return false;
  }
  const link = document.createElement('a');
  link.setAttribute('href', safeUrl);
  link.setAttribute('download', file.filename);
  link.rel = 'noopener noreferrer';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  return true;
}

type ToolCallLike = {
  id?: string;
  name?: string;
  result?: string;
};

type ContentChunkLike = {
  type?: string;
  toolCalls?: ToolCallLike[];
};

type MessageLike = {
  id?: string;
  metadata?: { contentChunks?: ContentChunkLike[] } | null;
};

function parseAttachmentResult(result: string): { filename?: string; file_url?: string } | null {
  try {
    const parsed = JSON.parse(result) as { filename?: string; file_url?: string };
    if (parsed && typeof parsed === 'object') {
      return parsed;
    }
  } catch {
    const filename = result.match(/["']filename["']\s*:\s*["']([^"']+)["']/)?.[1];
    const fileUrl = result.match(/["']file_url["']\s*:\s*["']([^"']+)["']/)?.[1];
    if (filename || fileUrl) {
      return { filename, file_url: fileUrl };
    }
  }
  return null;
}

export function fileExtension(filename: string): string {
  const dot = filename.lastIndexOf('.');
  if (dot <= 0 || dot === filename.length - 1) {
    return '';
  }
  return filename.slice(dot + 1).toLowerCase();
}

export function attachmentDownloadsFromToolCalls(toolCalls: Array<{ id?: string; name?: string; result?: string }>): SessionAttachmentFile[] {
  return collectSessionAttachmentFiles([
    {
      metadata: {
        contentChunks: [{ type: 'toolCalls', toolCalls }],
      },
    },
  ]);
}

export function collectSessionAttachmentFiles(messages: MessageLike[]): SessionAttachmentFile[] {
  const seen = new Set<string>();
  const files: SessionAttachmentFile[] = [];
  for (const message of messages) {
    const chunks = message.metadata?.contentChunks;
    if (!Array.isArray(chunks)) {
      continue;
    }
    for (const chunk of chunks) {
      if (chunk?.type !== 'toolCalls' || !Array.isArray(chunk.toolCalls)) {
        continue;
      }
      for (const tool of chunk.toolCalls) {
        if (tool?.name !== 'generate_attachment_file' || !tool.result) {
          continue;
        }
        const parsed = parseAttachmentResult(tool.result);
        const fileUrl = normalizeSafeDownloadUrl(parsed?.file_url || '');
        const filename = parsed?.filename || '';
        if (!fileUrl || !filename || seen.has(fileUrl)) {
          continue;
        }
        seen.add(fileUrl);
        files.push({
          id: tool.id || fileUrl,
          filename,
          fileUrl,
          ext: fileExtension(filename),
        });
      }
    }
  }
  return files;
}
