// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import {
  applyImeEnterDecision,
  createImeCompositionTracker,
  decideImeEnterAction,
  isImeCompositionKeyboardEvent,
  shouldSubmitChatOnEnter,
  useImeEnterGuard,
} from '../imeKeyboard';

describe('imeKeyboard', () => {
  it('treats composing Enter as IME commit, not send', () => {
    expect(isImeCompositionKeyboardEvent({ key: 'Enter', isComposing: true })).toBe(true);
    expect(
      isImeCompositionKeyboardEvent({
        key: 'Enter',
        nativeEvent: { isComposing: true },
      }),
    ).toBe(true);
    expect(isImeCompositionKeyboardEvent({ key: 'Enter', keyCode: 229 })).toBe(true);
    expect(
      isImeCompositionKeyboardEvent({
        key: 'Enter',
        nativeEvent: { keyCode: 229 },
      }),
    ).toBe(true);

    expect(shouldSubmitChatOnEnter({ key: 'Enter', isComposing: true })).toBe(false);
    expect(
      shouldSubmitChatOnEnter({
        key: 'Enter',
        nativeEvent: { isComposing: true },
      }),
    ).toBe(false);
    expect(shouldSubmitChatOnEnter({ key: 'Enter', keyCode: 229 })).toBe(false);

    expect(decideImeEnterAction({ key: 'Enter', isComposing: true })).toEqual({
      shouldSubmit: false,
      shouldPreventDefault: false,
    });
    expect(decideImeEnterAction({ key: 'Enter', keyCode: 229 })).toEqual({
      shouldSubmit: false,
      shouldPreventDefault: false,
    });
  });

  it('sends on a finished Enter and keeps Shift+Enter as newline', () => {
    expect(shouldSubmitChatOnEnter({ key: 'Enter' })).toBe(true);
    expect(
      shouldSubmitChatOnEnter({
        key: 'Enter',
        isComposing: false,
        nativeEvent: { isComposing: false, keyCode: 13 },
      }),
    ).toBe(true);
    expect(shouldSubmitChatOnEnter({ key: 'Enter', shiftKey: true })).toBe(false);
    expect(shouldSubmitChatOnEnter({ key: 'a' })).toBe(false);

    expect(decideImeEnterAction({ key: 'Enter' })).toEqual({
      shouldSubmit: true,
      shouldPreventDefault: true,
    });
    expect(decideImeEnterAction({ key: 'Enter', shiftKey: true })).toEqual({
      shouldSubmit: false,
      shouldPreventDefault: false,
    });
  });

  it('ignores the confirming Enter that some IMEs fire after compositionend', () => {
    vi.useFakeTimers();
    const tracker = createImeCompositionTracker();

    tracker.onCompositionStart();
    expect(shouldSubmitChatOnEnter({ key: 'Enter' }, tracker.isComposing())).toBe(false);

    tracker.onCompositionEnd();
    expect(shouldSubmitChatOnEnter({ key: 'Enter' }, tracker.isComposing())).toBe(false);

    vi.runAllTimers();
    expect(shouldSubmitChatOnEnter({ key: 'Enter' }, tracker.isComposing())).toBe(true);

    tracker.dispose();
    vi.useRealTimers();
  });

  it('prevents default on the confirming Enter after compositionend without sending', () => {
    vi.useFakeTimers();
    const tracker = createImeCompositionTracker();
    tracker.onCompositionStart();
    tracker.onCompositionEnd();

    const confirmingEnter = {
      key: 'Enter',
      isComposing: false,
      nativeEvent: { isComposing: false, keyCode: 13 },
    };
    expect(decideImeEnterAction(confirmingEnter, tracker.isComposing())).toEqual({
      shouldSubmit: false,
      shouldPreventDefault: true,
    });

    const preventDefault = vi.fn();
    expect(
      applyImeEnterDecision({ ...confirmingEnter, preventDefault }, tracker.isComposing()),
    ).toBe(false);
    expect(preventDefault).toHaveBeenCalledTimes(1);

    vi.runAllTimers();
    const sendPreventDefault = vi.fn();
    expect(
      applyImeEnterDecision({ ...confirmingEnter, preventDefault: sendPreventDefault }, tracker.isComposing()),
    ).toBe(true);
    expect(sendPreventDefault).toHaveBeenCalledTimes(1);

    tracker.dispose();
    vi.useRealTimers();
  });

  it('does not preventDefault while IME is still composing', () => {
    const preventDefault = vi.fn();
    expect(
      applyImeEnterDecision(
        { key: 'Enter', isComposing: true, keyCode: 229, preventDefault },
        true,
      ),
    ).toBe(false);
    expect(preventDefault).not.toHaveBeenCalled();
  });

  it('keeps composing if a new IME session starts before the end timer', () => {
    vi.useFakeTimers();
    const tracker = createImeCompositionTracker();

    tracker.onCompositionStart();
    tracker.onCompositionEnd();
    tracker.onCompositionStart();
    vi.runAllTimers();
    expect(tracker.isComposing()).toBe(true);
    expect(shouldSubmitChatOnEnter({ key: 'Enter' }, tracker.isComposing())).toBe(false);

    tracker.dispose();
    vi.useRealTimers();
  });
});

describe('useImeEnterGuard', () => {
  it('handleEnterKey prevents default on confirming Enter after compositionend without sending', () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useImeEnterGuard());

    act(() => {
      result.current.onCompositionStart();
      result.current.onCompositionEnd();
    });

    const preventDefault = vi.fn();
    expect(
      result.current.handleEnterKey({
        key: 'Enter',
        isComposing: false,
        nativeEvent: { isComposing: false, keyCode: 13 },
        preventDefault,
      }),
    ).toBe(false);
    expect(preventDefault).toHaveBeenCalledTimes(1);
    expect(
      result.current.decideEnter({
        key: 'Enter',
        isComposing: false,
        nativeEvent: { isComposing: false, keyCode: 13 },
      }),
    ).toEqual({ shouldSubmit: false, shouldPreventDefault: true });

    const composingPreventDefault = vi.fn();
    act(() => {
      result.current.onCompositionStart();
    });
    expect(
      result.current.handleEnterKey({
        key: 'Enter',
        isComposing: true,
        keyCode: 229,
        preventDefault: composingPreventDefault,
      }),
    ).toBe(false);
    expect(composingPreventDefault).not.toHaveBeenCalled();

    vi.useRealTimers();
  });
});
