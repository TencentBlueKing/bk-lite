'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react';
import styles from './conversation-drawer-shell.module.css';
import { shouldOpenConversationDrawer } from '../utils/drawerGesture';

const EDGE_GESTURE_WIDTH = 28;
const DIRECTION_LOCK_DISTANCE = 8;

type DragAxis = 'pending' | 'horizontal' | 'vertical';

interface DragState {
  axis: DragAxis;
  pointerId: number;
  startX: number;
  startY: number;
  startOffset: number;
  currentOffset: number;
  lastX: number;
  lastTime: number;
  velocityX: number;
}

interface ConversationDrawerShellProps {
  open: boolean;
  drawer: ReactNode;
  children: ReactNode;
  closeLabel: string;
  onOpen: () => void;
  onClose: () => void;
}

const clamp = (value: number, min: number, max: number) => (
  Math.min(Math.max(value, min), max)
);

export function ConversationDrawerShell({
  open,
  drawer,
  children,
  closeLabel,
  onOpen,
  onClose,
}: ConversationDrawerShellProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const stageContentRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const wasOpenRef = useRef(open);
  const dragRef = useRef<DragState | null>(null);
  const suppressMaskClickRef = useRef(false);
  const [drawerWidth, setDrawerWidth] = useState(0);
  const [dragOffset, setDragOffset] = useState<number | null>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const updateDrawerWidth = () => {
      setDrawerWidth(Math.min(root.getBoundingClientRect().width * 0.85, 320));
    };

    updateDrawerWidth();
    const resizeObserver = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(updateDrawerWidth);
    resizeObserver?.observe(root);
    window.addEventListener('resize', updateDrawerWidth);
    window.visualViewport?.addEventListener('resize', updateDrawerWidth);

    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener('resize', updateDrawerWidth);
      window.visualViewport?.removeEventListener('resize', updateDrawerWidth);
    };
  }, []);

  useEffect(() => {
    if (open && !wasOpenRef.current) {
      const activeElement = document.activeElement;
      const isTextEntry = activeElement instanceof HTMLInputElement
        || activeElement instanceof HTMLTextAreaElement;
      previousFocusRef.current = activeElement instanceof HTMLElement && !isTextEntry
        ? activeElement
        : null;
    }

    if (drawerRef.current) {
      drawerRef.current.inert = !open;
    }
    if (stageContentRef.current) {
      stageContentRef.current.inert = open;
    }

    if (open && !wasOpenRef.current) {
      requestAnimationFrame(() => {
        drawerRef.current
          ?.querySelector<HTMLElement>('aside')
          ?.focus({ preventScroll: true });
      });
    }

    if (!open && wasOpenRef.current) {
      previousFocusRef.current?.focus({ preventScroll: true });
      previousFocusRef.current = null;
    }
    wasOpenRef.current = open;
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, open]);

  const beginDrag = useCallback((event: ReactPointerEvent<HTMLElement>, startOffset: number) => {
    if (!event.isPrimary || (event.pointerType === 'mouse' && event.button !== 0) || drawerWidth <= 0) {
      return;
    }

    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      axis: 'pending',
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startOffset,
      currentOffset: startOffset,
      lastX: event.clientX,
      lastTime: event.timeStamp,
      velocityX: 0,
    };
    suppressMaskClickRef.current = false;
  }, [drawerWidth]);

  const handlePointerMove = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    const deltaX = event.clientX - drag.startX;
    const deltaY = event.clientY - drag.startY;

    if (drag.axis === 'pending') {
      if (Math.max(Math.abs(deltaX), Math.abs(deltaY)) < DIRECTION_LOCK_DISTANCE) return;
      drag.axis = Math.abs(deltaX) > Math.abs(deltaY) * 1.15 ? 'horizontal' : 'vertical';

      if (drag.axis === 'vertical') {
        dragRef.current = null;
        event.currentTarget.releasePointerCapture?.(event.pointerId);
        return;
      }
      suppressMaskClickRef.current = true;
    }

    if (drag.axis !== 'horizontal') return;
    if (event.cancelable) event.preventDefault();

    const nextOffset = clamp(drag.startOffset + deltaX, 0, drawerWidth);
    const elapsed = Math.max(event.timeStamp - drag.lastTime, 1);
    drag.velocityX = (event.clientX - drag.lastX) / elapsed;
    drag.lastX = event.clientX;
    drag.lastTime = event.timeStamp;
    drag.currentOffset = nextOffset;
    setDragOffset(nextOffset);
  }, [drawerWidth]);

  const finishDrag = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    if (drag.axis !== 'horizontal') {
      setDragOffset(null);
      return;
    }

    const shouldOpen = shouldOpenConversationDrawer({
      offset: drag.currentOffset,
      drawerWidth,
      velocityX: drag.velocityX,
    });

    setDragOffset(null);
    if (shouldOpen) {
      onOpen();
    } else {
      onClose();
    }
  }, [drawerWidth, onClose, onOpen]);

  const cancelDrag = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    setDragOffset(null);
  }, []);

  const offset = dragOffset ?? (open ? drawerWidth : 0);
  const progress = drawerWidth > 0 ? clamp(offset / drawerWidth, 0, 1) : 0;
  const dragging = dragOffset !== null;

  return (
    <div ref={rootRef} className={styles.root}>
      <div
        ref={drawerRef}
        className={`${styles.drawer} ${dragging ? styles.drawerDragging : ''}`}
        aria-hidden={!open}
        style={{
          width: drawerWidth || undefined,
          transform: `translate3d(${(progress - 1) * 18}px, 0, 0)`,
        }}
      >
        {drawer}
      </div>

      <div
        className={`${styles.stage} ${dragging ? styles.stageDragging : ''}`}
        style={{
          transform: `translate3d(${offset}px, 0, 0)`,
          borderRadius: `${progress * 16}px`,
          boxShadow: progress > 0 ? 'var(--shadow-navigation-drawer)' : 'none',
        }}
      >
        <div ref={stageContentRef} className={styles.stageContent}>
          {children}
        </div>

        <button
          type="button"
          className={styles.scrim}
          aria-label={closeLabel}
          aria-hidden={!open}
          tabIndex={open ? 0 : -1}
          style={{ opacity: progress }}
          onClick={() => {
            if (suppressMaskClickRef.current) {
              suppressMaskClickRef.current = false;
              return;
            }
            onClose();
          }}
          onPointerDown={(event) => beginDrag(event, drawerWidth)}
          onPointerMove={handlePointerMove}
          onPointerUp={finishDrag}
          onPointerCancel={cancelDrag}
        />
      </div>

      {!open && (
        <div
          className={styles.edgeGesture}
          style={{ width: EDGE_GESTURE_WIDTH }}
          aria-hidden="true"
          onPointerDown={(event) => beginDrag(event, 0)}
          onPointerMove={handlePointerMove}
          onPointerUp={finishDrag}
          onPointerCancel={cancelDrag}
        />
      )}
    </div>
  );
}
