'use client';

import React, { useState, useRef, useEffect, Suspense } from 'react';
import type { ChatProps } from './chatProps';
import { ChatState, isPlatformMode } from '@webchat/core';
import { createFloatingButtonChatCallbacks } from './floatingButtonCallbacks';
import { ConversationSkeleton } from './components/ConversationSkeleton';
import { WC } from './chrome';

const Chat = React.lazy(async () => {
  const mod = await import('./Chat');
  return { default: mod.Chat };
});
const PlatformChat = React.lazy(async () => {
  const mod = await import('./PlatformChat');
  return { default: mod.PlatformChat };
});

/**
 * Floating launcher options plus the complete Chat configuration contract.
 * `onChatStateChange` takes precedence over `onStateChange`; closing the Chat
 * notifies `onClose` before the floating container is hidden.
 */
export interface FloatingButtonProps extends ChatProps {
  buttonText?: string;
  buttonIcon?: React.ReactNode;
  buttonStyle?: React.CSSProperties;
  buttonClassName?: string;
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
  onChatStateChange?: (state: ChatState) => void;
  userId?: string;
  teamId?: string;
  onAccessDenied?: () => void;
  canManageAgents?: boolean;
  manageAgentsUrl?: string;
}

export const FloatingButton = React.memo(React.forwardRef<HTMLDivElement, FloatingButtonProps>((props, _ref) => {
  const {
    buttonText,
    buttonIcon = (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 3a9 9 0 0 0-7.8 13.5L3 21l4.7-1.1A9 9 0 1 0 12 3zm-3.2 8.2a1.1 1.1 0 1 1 0-2.2 1.1 1.1 0 0 1 0 2.2zm3.2 0a1.1 1.1 0 1 1 0-2.2 1.1 1.1 0 0 1 0 2.2zm3.2 0a1.1 1.1 0 1 1 0-2.2 1.1 1.1 0 0 1 0 2.2z" />
      </svg>
    ),
    buttonStyle,
    buttonClassName,
    position = 'bottom-right',
    onChatStateChange,
    onStateChange,
    onClose,
    userId,
    teamId,
    onAccessDenied,
    canManageAgents,
    manageAgentsUrl,
    ...chatProps
  } = props;

  const [isOpen, setIsOpen] = useState(false);
  const [hasOpened, setHasOpened] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);
  const [isPanelFullscreen, setIsPanelFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dragStartY = useRef(0);
  const initialBottom = useRef(0);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        // Optionally close on outside click
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragStartY.current = e.clientY;
    initialBottom.current = dragOffset;
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging) return;
    const deltaY = dragStartY.current - e.clientY;
    const newBottom = initialBottom.current + deltaY;
    const maxBottom = window.innerHeight - 100;
    const clampedBottom = Math.max(0, Math.min(newBottom, maxBottom));
    setDragOffset(clampedBottom);
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
    return undefined;
  }, [isDragging]);

  useEffect(() => {
    if (!isOpen || !isPanelFullscreen) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsPanelFullscreen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [isOpen, isPanelFullscreen]);

  const positionClasses: Record<string, string> = {
    'bottom-right': 'bottom-5 right-2',
    'bottom-left': 'bottom-5 left-2',
    'top-right': 'top-5 right-2',
    'top-left': 'top-5 left-2',
  };
  const close = React.useCallback(() => {
    setIsOpen(false);
    setIsPanelFullscreen(false);
  }, []);
  const open = React.useCallback(() => {
    setHasOpened(true);
    setIsOpen(true);
  }, []);
  const handleAccessDenied = React.useCallback(() => {
    setHidden(true);
    setIsOpen(false);
    setIsPanelFullscreen(false);
    onAccessDenied?.();
  }, [onAccessDenied]);
  const chatCallbacks = React.useMemo(
    () =>
      createFloatingButtonChatCallbacks({
        onChatStateChange,
        onStateChange,
        onClose,
        close,
      }),
    [close, onChatStateChange, onClose, onStateChange]
  );

  if (hidden) {
    return null;
  }

  if (isPlatformMode(chatProps) && chatProps.platform) {
    return (
      <Suspense fallback={null}>
        <PlatformChat
          {...chatProps}
          platform={chatProps.platform}
          userId={userId}
          teamId={teamId}
          canManageAgents={canManageAgents}
          manageAgentsUrl={manageAgentsUrl}
          onAccessDenied={handleAccessDenied}
          {...chatCallbacks}
        />
      </Suspense>
    );
  }

  return (
    <div
      ref={containerRef}
      className={
        isPanelFullscreen && isOpen
          ? 'fixed inset-0 z-[2000] font-sans'
          : `fixed z-50 font-sans ${positionClasses[position]}`
      }
      style={isPanelFullscreen && isOpen ? undefined : { bottom: `calc(1.5rem + ${dragOffset}px)` }}
    >
      {/* Chat Panel - 固定在视口边缘 */}
      {hasOpened && isPanelFullscreen && isOpen && (
        <div className="fixed inset-0 z-[1990]" style={{ background: WC.overlay }} />
      )}
      {hasOpened && (
        <div
          className={`overflow-hidden ${isOpen ? '' : 'hidden'} ${
            isPanelFullscreen ? 'fixed inset-0 z-[2000] h-full w-full rounded-none' : 'fixed bottom-4 right-4 z-50 rounded-lg'
          }`}
          style={{
            height: isPanelFullscreen ? undefined : '650px',
            maxHeight: isPanelFullscreen ? undefined : 'calc(100vh - 2rem)',
            boxShadow: isPanelFullscreen ? 'none' : WC.shadow,
          }}
          aria-hidden={!isOpen}
        >
          <Suspense
            fallback={
              <div className="h-full w-96 p-4" style={{ background: WC.white }}>
                <ConversationSkeleton />
              </div>
            }
          >
            <Chat
              {...chatProps}
              fullscreen={isPanelFullscreen}
              onFullscreenChange={setIsPanelFullscreen}
              wideLayout={isPanelFullscreen}
              {...chatCallbacks}
            />
          </Suspense>
        </div>
      )}

      {/* Floating Button - 打开时隐藏 */}
      {!isOpen && (
        <button
          ref={buttonRef}
          className={
            buttonClassName ||
            `absolute bottom-0 right-0 flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border-none font-inherit ${
              isDragging ? 'cursor-grabbing' : 'cursor-grab'
            }`
          }
          style={{
            background: WC.indigo,
            color: WC.onPrimary,
            ...buttonStyle,
          }}
          onClick={() => !isDragging && (isOpen ? close() : open())}
          onMouseDown={handleMouseDown}
          title="打开对话"
          aria-label="打开对话"
        >
          <span className="pointer-events-none flex items-center justify-center">
            {buttonIcon}
          </span>
          {buttonText && (
            <span className="text-xs font-semibold whitespace-nowrap tracking-widest ml-1 pointer-events-none">
              {buttonText}
            </span>
          )}
        </button>
      )}
    </div>
  );
}));

FloatingButton.displayName = 'FloatingButton';
