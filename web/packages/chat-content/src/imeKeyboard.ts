import { useEffect, useRef } from 'react';
import { createImeCompositionTracker, shouldSubmitChatOnEnter, decideImeEnterAction, applyImeEnterDecision, type ImeKeyboardEventLike, type ImeEnterKeyEvent } from './ime';
export * from './ime';
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
