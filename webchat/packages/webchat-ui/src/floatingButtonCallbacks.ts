import type { ChatState } from '@webchat/core';

type StateChangeCallback = (state: ChatState) => void;

interface FloatingButtonCallbackOptions {
  onChatStateChange?: StateChangeCallback;
  onStateChange?: StateChangeCallback;
  onClose?: () => void;
  close: () => void;
}

interface FloatingButtonChatCallbacks {
  onStateChange?: StateChangeCallback;
  onClose: () => void;
}

/** Compose Chat callbacks with the floating container's close behavior. */
export function createFloatingButtonChatCallbacks({
  onChatStateChange,
  onStateChange,
  onClose,
  close,
}: FloatingButtonCallbackOptions): FloatingButtonChatCallbacks {
  return {
    onStateChange: onChatStateChange ?? onStateChange,
    onClose: () => {
      try {
        onClose?.();
      } finally {
        close();
      }
    },
  };
}
