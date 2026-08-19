'use client';

import React from 'react';
import { WC } from '../chrome';

export interface PillComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  placeholder?: string;
  loading?: boolean;
  onCancel?: () => void;
  imageSlot?: React.ReactNode;
  onPaste?: React.ClipboardEventHandler<HTMLInputElement>;
}

export const PillComposer = React.memo(function PillComposer({
  value,
  onChange,
  onSubmit,
  placeholder = '请输入消息...',
  loading = false,
  onCancel,
  imageSlot,
  onPaste,
}: PillComposerProps) {
  const submit = () => {
    const text = value.trim();
    if (!text || loading) return;
    onSubmit(text);
  };

  return (
    <div className="relative">
      <div
        className="absolute left-3 top-1/2 z-10 -translate-y-1/2"
        style={{ color: WC.muted }}
      >
        {imageSlot ?? (
          <span className="pointer-events-none">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="M21 15l-5-5L5 21" />
            </svg>
          </span>
        )}
      </div>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onPaste={onPaste}
        placeholder={placeholder}
        disabled={loading}
        className="h-10 w-full rounded-full py-0 pl-9 pr-11 text-sm outline-none"
        style={{
          border: `1px solid ${WC.botBorder}`,
          background: WC.page,
          color: WC.botText,
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            submit();
          }
        }}
      />
      <button
        type="button"
        title={loading ? '停止' : '发送'}
        onClick={loading ? onCancel : submit}
        className="absolute right-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-full border-none"
        style={{ background: WC.indigo, color: WC.onPrimary }}
      >
        {loading ? (
          <span className="block h-2.5 w-2.5 rounded-[2px]" style={{ background: WC.onPrimary }} />
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        )}
      </button>
    </div>
  );
});
