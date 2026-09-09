export const MEMORY_LIST_CONTENT_PREVIEW_CHARS = 240;
export const MEMORY_PREVIEW_CONTENT_LIMIT = 80_000;
export const MEMORY_INLINE_EDIT_MAX_CHARS = 200_000;
export const MEMORY_DOCUMENT_PAGE_CHARS = 32_000;

export function formatMemoryContentSize(length: number, locale = 'zh'): string {
  const chars = Math.max(0, Number(length) || 0);
  if (locale === 'en') {
    if (chars >= 1_000_000) {
      return `${(chars / 1_000_000).toFixed(1)}M chars`;
    }
    if (chars >= 1_000) {
      return `${(chars / 1_000).toFixed(1)}K chars`;
    }
    return `${chars} chars`;
  }
  if (chars >= 10_000) {
    return `${(chars / 10_000).toFixed(1)} 万字`;
  }
  return `${chars} 字`;
}

export function canInlineEditMemory(contentLength?: number): boolean {
  return (contentLength ?? 0) <= MEMORY_INLINE_EDIT_MAX_CHARS;
}

export function shouldMarkdownRenderMemory(contentLength?: number): boolean {
  return (contentLength ?? 0) <= MEMORY_PREVIEW_CONTENT_LIMIT;
}

export function shouldPageMemoryDocument(contentLength?: number): boolean {
  return (contentLength ?? 0) > MEMORY_PREVIEW_CONTENT_LIMIT;
}

export function memoryDocumentPageCount(contentLength: number, pageSize = MEMORY_DOCUMENT_PAGE_CHARS): number {
  const length = Math.max(0, Number(contentLength) || 0);
  const size = Math.max(1, pageSize);
  return Math.max(1, Math.ceil(length / size));
}

export function memoryDocumentPageOffset(page: number, pageSize = MEMORY_DOCUMENT_PAGE_CHARS): number {
  return Math.max(0, page - 1) * Math.max(1, pageSize);
}

/** 与服务端 Python `len(str)` 对齐的 Unicode code point 长度。 */
export function memoryContentLength(value: string): number {
  return Array.from(value).length;
}

export function buildMemoryDocumentHref(spaceId: number, memoryId: number, options?: { edit?: boolean }): string {
  const params = new URLSearchParams({
    id: String(spaceId),
    memoryId: String(memoryId),
  });
  if (options?.edit) {
    params.set('edit', '1');
  }
  return `/opspilot/memory/document?${params.toString()}`;
}

export function openMemoryDocument(spaceId: number, memoryId: number, options?: { edit?: boolean }): void {
  window.open(buildMemoryDocumentHref(spaceId, memoryId, options), '_blank', 'noopener,noreferrer');
}
