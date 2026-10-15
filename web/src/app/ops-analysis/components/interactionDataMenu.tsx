'use client';

import React, { useEffect } from 'react';

interface InteractionDataMenuProps {
  open: boolean;
  x: number;
  y: number;
  label: string;
  onSelect: () => void;
  onClose: () => void;
}

const InteractionDataMenu: React.FC<InteractionDataMenuProps> = ({
  open,
  x,
  y,
  label,
  onSelect,
  onClose,
}) => {
  useEffect(() => {
    if (!open) return undefined;
    const close = () => onClose();
    window.addEventListener('pointerdown', close);
    window.addEventListener('scroll', close, true);
    return () => {
      window.removeEventListener('pointerdown', close);
      window.removeEventListener('scroll', close, true);
    };
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div
      role="menu"
      className="fixed z-[80] min-w-36 rounded-md border border-(--color-border-1) bg-(--color-bg-1) py-1 shadow-md"
      style={{ left: x, top: y }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <button
        type="button"
        role="menuitem"
        className="block w-full cursor-pointer px-3 py-1.5 text-left text-xs text-(--color-text-1) hover:bg-(--color-fill-1)"
        onClick={() => {
          onSelect();
          onClose();
        }}
      >
        {label}
      </button>
    </div>
  );
};

export default InteractionDataMenu;
