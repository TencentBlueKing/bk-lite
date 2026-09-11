import {
  createImeCompositionTracker,
  isImeCompositionKeyboardEvent,
  shouldSubmitChatOnEnter,
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
