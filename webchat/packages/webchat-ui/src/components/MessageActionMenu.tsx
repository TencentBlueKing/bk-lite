import { useLayoutEffect, useRef, type ReactNode, type RefObject } from 'react';

interface Props {
  anchor: RefObject<HTMLButtonElement>;
  label: string;
  onClose: () => void;
  children: ReactNode;
}

export function MessageActionMenu({ anchor, label, onClose, children }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const menu = ref.current;
    const button = anchor.current;
    if (!menu || !button) return;
    // Keep the small menu outside the scroll container's clipping region.
    if (menu.showPopover) {
      menu.popover = 'manual';
      menu.showPopover();
    }
    const place = () => {
      const rect = button.getBoundingClientRect();
      const height = menu.offsetHeight;
      const below = rect.bottom + 4;
      menu.style.top = `${below + height <= window.innerHeight - 4 ? below : Math.max(4, rect.top - height - 4)}px`;
      menu.style.left = `${Math.max(4, Math.min(rect.left, window.innerWidth - menu.offsetWidth - 4))}px`;
    };
    place();
    menu.querySelector('button')?.focus({ preventScroll: true });
    const outside = (event: Event) => {
      if (event.target instanceof Node && !menu.contains(event.target) && !button.contains(event.target)) onClose();
    };
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('focusin', outside, true);
    window.addEventListener('resize', place);
    document.addEventListener('scroll', place, true);
    return () => {
      document.removeEventListener('pointerdown', outside, true);
      document.removeEventListener('focusin', outside, true);
      window.removeEventListener('resize', place);
      document.removeEventListener('scroll', place, true);
    };
  }, [anchor, onClose]);
  return (
    <div ref={ref} role="menu" aria-label={label}
      className="fixed bottom-auto right-auto z-[2150] m-0 box-border w-max min-w-[100px] rounded-[14px] border border-solid border-[var(--color-border-1,#e5e5e5)] bg-[var(--color-bg,#fff)] p-1 text-[var(--color-text-1,#222)] shadow-md"
      onKeyDown={event => {
        if (event.key === 'Escape') {
          event.preventDefault(); event.stopPropagation(); onClose(); anchor.current?.focus(); return;
        }
        if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
        event.preventDefault();
        const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
        const index = buttons.findIndex(button => button === document.activeElement);
        buttons[(index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus();
      }}
    >{children}</div>
  );
}
