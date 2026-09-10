import { describe, expect, it } from 'vitest';

import {
  buildMemoryDocumentHref,
  canInlineEditMemory,
  formatMemoryContentSize,
  MEMORY_INLINE_EDIT_MAX_CHARS,
  memoryContentLength,
  memoryDocumentPageCount,
  memoryDocumentPageOffset,
  shouldMarkdownRenderMemory,
  shouldPageMemoryDocument,
} from '../memoryContent';

describe('memory content size helpers', () => {
  it('formats Chinese and English sizes', () => {
    expect(formatMemoryContentSize(240, 'zh')).toBe('240 字');
    expect(formatMemoryContentSize(50_000, 'zh')).toBe('5.0 万字');
    expect(formatMemoryContentSize(240, 'en')).toBe('240 chars');
    expect(formatMemoryContentSize(12_000, 'en')).toBe('12.0K chars');
    expect(formatMemoryContentSize(1_200_000, 'en')).toBe('1.2M chars');
  });

  it('blocks inline edit above the browser-safe cap', () => {
    expect(canInlineEditMemory(1_000)).toBe(true);
    expect(canInlineEditMemory(MEMORY_INLINE_EDIT_MAX_CHARS)).toBe(true);
    expect(canInlineEditMemory(MEMORY_INLINE_EDIT_MAX_CHARS + 1)).toBe(false);
  });

  it('only markdown-renders memories within the preview cap', () => {
    expect(shouldMarkdownRenderMemory(80_000)).toBe(true);
    expect(shouldMarkdownRenderMemory(80_001)).toBe(false);
  });

  it('pages large documents instead of mounting the full text', () => {
    expect(shouldPageMemoryDocument(80_000)).toBe(false);
    expect(shouldPageMemoryDocument(80_001)).toBe(true);
    expect(memoryDocumentPageCount(32_000)).toBe(1);
    expect(memoryDocumentPageCount(32_001)).toBe(2);
    expect(memoryDocumentPageCount(9_400_000)).toBe(294);
    expect(memoryDocumentPageOffset(1)).toBe(0);
    expect(memoryDocumentPageOffset(2)).toBe(32_000);
  });

  it('counts unicode code points like the server', () => {
    expect(memoryContentLength('abc')).toBe(3);
    expect(memoryContentLength('你好')).toBe(2);
    expect(memoryContentLength('🙂')).toBe(1);
  });

  it('builds a standalone document href', () => {
    expect(buildMemoryDocumentHref(3, 12)).toBe('/opspilot/memory/document?id=3&memoryId=12');
    expect(buildMemoryDocumentHref(3, 12, { edit: true })).toBe(
      '/opspilot/memory/document?id=3&memoryId=12&edit=1'
    );
  });
});
