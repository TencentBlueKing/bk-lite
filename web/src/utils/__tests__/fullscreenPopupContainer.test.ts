import { afterEach, describe, expect, it } from 'vitest';
import { fullscreenPopupContainer } from '@/utils/fullscreenPopupContainer';

describe('fullscreenPopupContainer', () => {
  afterEach(() => {
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => null,
    });
  });

  it('stays on body outside fullscreen and follows the fullscreen element', () => {
    expect(fullscreenPopupContainer()).toBe(document.body);
    const stage = document.createElement('div');
    document.body.appendChild(stage);
    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () => stage,
    });
    expect(fullscreenPopupContainer()).toBe(stage);
    stage.remove();
  });
});