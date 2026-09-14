/** Keyboard-like events used by chat composers (React synthetic or native). */
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

/**
 * IME composition (pinyin, etc.) uses Enter to commit the current candidate.
 * Those key events must not be treated as "send".
 */
export function isImeCompositionKeyboardEvent(event: ImeKeyboardEventLike): boolean {
  const native = event.nativeEvent;
  const keyCode = event.keyCode ?? native?.keyCode;
  return Boolean(event.isComposing || native?.isComposing || keyCode === 229);
}

export function shouldSubmitChatOnEnter(
  event: ImeKeyboardEventLike,
  composingSession = false,
): boolean {
  if (event.key !== 'Enter' || event.shiftKey) {
    return false;
  }
  if (composingSession || isImeCompositionKeyboardEvent(event)) {
    return false;
  }
  return true;
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
