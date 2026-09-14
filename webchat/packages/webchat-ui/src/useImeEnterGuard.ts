import { useEffect, useRef } from 'react';
import {
  createImeCompositionTracker,
  shouldSubmitChatOnEnter,
  type ImeKeyboardEventLike,
} from '@webchat/core';

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
  };
}
