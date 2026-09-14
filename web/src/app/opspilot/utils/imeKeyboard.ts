import { useEffect, useRef } from 'react';

/** Keyboard-like events used by chat composers (React synthetic or Ant Design). */
export type ImeKeyboardEventLike = {
  key?: string;
  shiftKey?: boolean;
  isComposing?: boolean;
  keyCode?: number;
  nativeEvent?: {
    isComposing?: boolean;
    keyCode?: number;
  };
};

export type ImeEnterKeyEvent = ImeKeyboardEventLike & {
  preventDefault: () => void;
};

export type ImeEnterDecision = {
  shouldSubmit: boolean;
  shouldPreventDefault: boolean;
};

/**
 * IME composition (pinyin, etc.) uses Enter to commit the current candidate.
 * Those key events must not be treated as "send".
 */
export function isImeCompositionKeyboardEvent(event: ImeKeyboardEventLike): boolean {
  const native = event.nativeEvent;
  const keyCode = event.keyCode ?? native?.keyCode;
  return Boolean(event.isComposing || native?.isComposing || keyCode === 229);
}

/**
 * Decide whether an Enter should send, and whether to preventDefault.
 *
 * 1. Still composing (`isComposing` / keyCode 229): do not send, do not
 *    preventDefault — leave the IME confirmation alone.
 * 2. Tracker still composing, but the event is a normal Enter (the confirming
 *    key after `compositionend`): preventDefault so TextArea does not insert
 *    a newline, and do not send.
 * 3. A real sendable Enter: preventDefault and send. Shift+Enter stays a newline.
 */
export function decideImeEnterAction(
  event: ImeKeyboardEventLike,
  composingSession = false,
): ImeEnterDecision {
  if (event.key !== 'Enter' || event.shiftKey) {
    return { shouldSubmit: false, shouldPreventDefault: false };
  }
  if (isImeCompositionKeyboardEvent(event)) {
    return { shouldSubmit: false, shouldPreventDefault: false };
  }
  if (composingSession) {
    return { shouldSubmit: false, shouldPreventDefault: true };
  }
  return { shouldSubmit: true, shouldPreventDefault: true };
}

export function shouldSubmitChatOnEnter(
  event: ImeKeyboardEventLike,
  composingSession = false,
): boolean {
  return decideImeEnterAction(event, composingSession).shouldSubmit;
}

/** Apply the Enter decision to the event and return whether the caller should send. */
export function applyImeEnterDecision(
  event: ImeEnterKeyEvent,
  composingSession = false,
): boolean {
  const decision = decideImeEnterAction(event, composingSession);
  if (decision.shouldPreventDefault) {
    event.preventDefault();
  }
  return decision.shouldSubmit;
}

/**
 * Tracks IME composition and keeps it true until after the confirming Enter.
 * Some browsers fire that Enter after `compositionend` with `isComposing=false`.
 */
export function createImeCompositionTracker() {
  let composing = false;
  let endTimer: ReturnType<typeof setTimeout> | null = null;

  const clearEndTimer = () => {
    if (endTimer != null) {
      clearTimeout(endTimer);
      endTimer = null;
    }
  };

  return {
    onCompositionStart() {
      clearEndTimer();
      composing = true;
    },
    onCompositionEnd() {
      clearEndTimer();
      endTimer = setTimeout(() => {
        composing = false;
        endTimer = null;
      }, 0);
    },
    isComposing() {
      return composing;
    },
    dispose() {
      clearEndTimer();
    },
  };
}

export function useImeEnterGuard() {
  const trackerRef = useRef<ReturnType<typeof createImeCompositionTracker> | null>(null);
  if (trackerRef.current == null) {
    trackerRef.current = createImeCompositionTracker();
  }
  const tracker = trackerRef.current;

  useEffect(() => () => tracker.dispose(), [tracker]);

  return {
    onCompositionStart: tracker.onCompositionStart,
    onCompositionEnd: tracker.onCompositionEnd,
    shouldSubmitOnEnter: (event: ImeKeyboardEventLike) =>
      shouldSubmitChatOnEnter(event, tracker.isComposing()),
    decideEnter: (event: ImeKeyboardEventLike) =>
      decideImeEnterAction(event, tracker.isComposing()),
    handleEnterKey: (event: ImeEnterKeyEvent) =>
      applyImeEnterDecision(event, tracker.isComposing()),
  };
}
