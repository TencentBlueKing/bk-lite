'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Chat } from './Chat';
import { WebChatConfig, ChatState } from '@webchat/core';

export interface FloatingButtonProps extends WebChatConfig {
  buttonText?: string;
  buttonIcon?: React.ReactNode;
  buttonStyle?: React.CSSProperties;
  buttonClassName?: string;
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
  onChatStateChange?: (state: ChatState) => void;
}

export const FloatingButton = React.forwardRef<any, FloatingButtonProps>((props, _ref) => {
  const {
    buttonText,
    buttonIcon = '💬',
    buttonStyle,
    buttonClassName,
    position = 'bottom-right',
    onChatStateChange,
    ...chatProps
  } = props;

  const [isOpen, setIsOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<any>(null);
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

  const positionClasses: Record<string, string> = {
    'bottom-right': 'bottom-6 right-6',
    'bottom-left': 'bottom-6 left-6',
    'top-right': 'top-6 right-6',
    'top-left': 'top-6 left-6',
  };

  return (
    <div
      ref={containerRef}
      className={`fixed z-50 font-sans ${positionClasses[position]}`}
      style={{ bottom: `calc(1.5rem + ${dragOffset}px)` }}
    >
      {/* Chat Panel - 固定在视口边缘 */}
      {isOpen && (
        <div
          className="fixed bottom-4 right-4 w-96 shadow-2xl rounded-lg overflow-hidden transition-all duration-300"
          style={{ height: '650px', maxHeight: 'calc(100vh - 2rem)' }}
        >
          <Chat
            ref={chatRef}
            {...chatProps}
            onStateChange={onChatStateChange}
            onClose={() => setIsOpen(false)}
          />
        </div>
      )}

      {/* Floating Button - 打开时隐藏 */}
      {!isOpen && (
        <button
          ref={buttonRef}
          className={
            buttonClassName ||
            `absolute bottom-0 right-0 w-16 h-16 rounded-full flex items-center justify-center text-2xl border-none cursor-pointer transition-all duration-300 font-inherit bg-gradient-to-br from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 shadow-lg hover:shadow-2xl hover:scale-110 ${
              isDragging ? 'cursor-grabbing' : 'cursor-grab'
            }`
          }
          style={buttonStyle}
          onClick={() => !isDragging && setIsOpen(!isOpen)}
          onMouseDown={handleMouseDown}
          title="Open chat"
          aria-label="Toggle chat"
        >
          <span className="flex items-center justify-center text-xl drop-shadow-md pointer-events-none">
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
});

FloatingButton.displayName = 'FloatingButton';
