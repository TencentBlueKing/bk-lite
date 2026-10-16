'use client';

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

const VIEWPORT_MARGIN = 8;

interface InteractionDataMenuProps {
  open: boolean;
  x: number;
  y: number;
  label: string;
  onSelect: () => void;
  onClose: () => void;
  /** scene：3D 场景标签式文字样式 */
  variant?: 'default' | 'scene';
  /** 用于计算大屏缩放比例的组件容器 */
  anchorRef?: React.RefObject<HTMLElement | null>;
}

const MIN_SCALE = 0.6;
const MAX_SCALE = 2;

const getEffectiveScale = (el?: HTMLElement | null) => {
  if (!el || !el.offsetWidth) return 1;
  const scale = el.getBoundingClientRect().width / el.offsetWidth;
  if (!Number.isFinite(scale) || scale <= 0) return 1;
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale));
};

const InteractionDataMenu: React.FC<InteractionDataMenuProps> = ({
  open,
  x,
  y,
  label,
  onSelect,
  onClose,
  variant = 'default',
  anchorRef,
}) => {
  const [scale, setScale] = useState(1);
  const isScene = variant === 'scene';
  const menuRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: x, top: y });

  useLayoutEffect(() => {
    if (open) setScale(getEffectiveScale(anchorRef?.current));
  }, [anchorRef, open, x, y]);

  useLayoutEffect(() => {
    if (!open || !menuRef.current) return;
    const { width, height } = menuRef.current.getBoundingClientRect();
    const maxLeft = window.innerWidth - width - VIEWPORT_MARGIN;
    const maxTop = window.innerHeight - height - VIEWPORT_MARGIN;
    const left = x > maxLeft ? x - width : x;
    const top = y > maxTop ? y - height : y;
    setPosition({
      left: Math.max(VIEWPORT_MARGIN, Math.min(left, maxLeft)),
      top: Math.max(VIEWPORT_MARGIN, Math.min(top, maxTop)),
    });
  }, [open, x, y, scale]);

  useEffect(() => {
    if (!open) return undefined;
    const close = () => onClose();
    const closeOnOutside = (event: PointerEvent) => {
      if (menuRef.current?.contains(event.target as Node)) return;
      onClose();
    };
    window.addEventListener('pointerdown', closeOnOutside);
    window.addEventListener('scroll', close, true);
    return () => {
      window.removeEventListener('pointerdown', closeOnOutside);
      window.removeEventListener('scroll', close, true);
    };
  }, [onClose, open]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      className={
        isScene
          ? 'fixed z-[1100] flex flex-col'
          : 'fixed z-[80] min-w-36 rounded-md border border-(--color-border-1) bg-(--color-bg-1) py-1 shadow-md'
      }
      style={{
        left: position.left,
        top: position.top,
        ...(isScene ? { fontSize: 12 * scale } : {}),
      }}
    >
      <button
        type="button"
        role="menuitem"
        className={
          isScene
            ? 'block w-fit cursor-pointer border-0 bg-transparent p-0 text-left text-[#7fd4ff] [text-shadow:0_1px_3px_rgba(0,0,0,0.8)] [border-bottom:1px_solid_rgba(127,212,255,0.45)] hover:text-[#b5e8ff] hover:[border-bottom-color:#7fd4ff] focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-[#7fd4ff]'
            : 'block w-full cursor-pointer px-3 py-1.5 text-left text-xs text-(--color-text-1) hover:bg-(--color-fill-1)'
        }
        style={
          isScene
            ? { fontSize: 'inherit', lineHeight: 1.4 }
            : undefined
        }
        onClick={() => {
          onSelect();
          onClose();
        }}
      >
        {isScene ? (
          <>
            {label}
            <span aria-hidden="true"> ↗</span>
          </>
        ) : (
          label
        )}
      </button>
    </div>,
    document.body
  );
};

export default InteractionDataMenu;
