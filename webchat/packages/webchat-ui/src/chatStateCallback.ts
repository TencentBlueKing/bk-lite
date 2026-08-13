import type { ChatState } from '@webchat/core';
import { useLayoutEffect, useRef } from 'react';

type StateChangeCallback = (state: ChatState) => void;

/** Keep an effect-owned listener pointed at the latest React callback prop. */
export function useLatestChatStateCallback(callback?: StateChangeCallback) {
  const callbackRef = useRef(callback);
  useLayoutEffect(() => {
    callbackRef.current = callback;
  }, [callback]);
  return callbackRef;
}
