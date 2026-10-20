import React from 'react';

interface SpinProps {
  fullscreen?: boolean;
  label?: string;
}

const Spin = ({ fullscreen = false, label = 'Loading' }: SpinProps) => (
  <div
    role="status"
    aria-label={label}
    className={fullscreen
      ? 'fixed inset-0 z-[999] flex items-center justify-center bg-[var(--color-bg)]'
      : 'inline-flex items-center justify-center'}
  >
    <span
      aria-hidden="true"
      className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-fill-3)] border-t-[var(--color-text-3)] motion-reduce:animate-none"
    />
  </div>
);

export default Spin;
