import { describe, expect, it } from 'vitest';
import {
  canStartCarouselPreview,
  manualPreviewStep,
  relocatePreviewIndexByKeys,
  shouldAutoOpenCarouselEditor,
} from '@/app/ops-analysis/utils/carouselPreview';

describe('carousel preview', () => {
  it('falls back to the next item, or the previous one at the end', () => {
    expect(relocatePreviewIndexByKeys(['a', 'b', 'c'], 1, ['a', 'c'])).toBe(1);
    expect(relocatePreviewIndexByKeys(['a', 'b', 'c'], 2, ['a', 'b'])).toBe(1);
    expect(relocatePreviewIndexByKeys(['a', 'b', 'c'], 2, ['b', 'c'])).toBe(1);
    expect(relocatePreviewIndexByKeys(['a', 'b', 'c'], 0, [])).toBe(-1);
  });

  it('keeps the same canvas when the list is reordered', () => {
    expect(relocatePreviewIndexByKeys(['a', 'b', 'c'], 0, ['b', 'c', 'a'])).toBe(2);
  });

  it('opens the editor only after the new empty list has loaded', () => {
    const request = { id: '2', nonce: 1 };
    expect(shouldAutoOpenCarouselEditor({
      request,
      appliedNonce: 0,
      loadedId: '1',
      loading: false,
      itemCount: 0,
      canEdit: true,
    })).toBe(false);
    expect(shouldAutoOpenCarouselEditor({
      request,
      appliedNonce: 0,
      loadedId: '2',
      loading: true,
      itemCount: 0,
      canEdit: true,
    })).toBe(false);
    expect(shouldAutoOpenCarouselEditor({
      request,
      appliedNonce: 0,
      loadedId: '2',
      loading: false,
      itemCount: 0,
      canEdit: false,
    })).toBe(false);
    expect(shouldAutoOpenCarouselEditor({
      request,
      appliedNonce: 0,
      loadedId: '2',
      loading: false,
      itemCount: 2,
      canEdit: true,
    })).toBe(false);
    expect(shouldAutoOpenCarouselEditor({
      request,
      appliedNonce: 0,
      loadedId: '2',
      loading: false,
      itemCount: 0,
      canEdit: true,
    })).toBe(true);
    expect(shouldAutoOpenCarouselEditor({
      request,
      appliedNonce: 1,
      loadedId: '2',
      loading: false,
      itemCount: 0,
      canEdit: true,
    })).toBe(false);
  });

  it('refuses playback while the editor is open and steps through every row', () => {
    expect(canStartCarouselPreview(true)).toBe(false);
    expect(canStartCarouselPreview(false)).toBe(true);
    expect(manualPreviewStep(3, 2, 1)).toBe(0);
    expect(manualPreviewStep(3, 0, -1)).toBe(2);
  });
});