import type { ChatProps } from './Chat';

interface FloatingButtonCallbackOptions {
  onChatStateChange?: ChatProps['onStateChange'];
  onStateChange?: ChatProps['onStateChange'];
  onClose?: ChatProps['onClose'];
  close: () => void;
}

/** Compose Chat callbacks with the floating container's close behavior. */
export function createFloatingButtonChatCallbacks({
  onChatStateChange,
  onStateChange,
  onClose,
  close,
}: FloatingButtonCallbackOptions): Pick<ChatProps, 'onStateChange' | 'onClose'> {
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
