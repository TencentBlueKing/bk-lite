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

const COMPOSER_HEIGHT = 40;
const SIDE_CONTROL = 28;
const SIDE_GAP = 6;

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
    <div
      style={{
        position: 'relative',
        height: COMPOSER_HEIGHT,
        width: '100%',
        borderRadius: 9999,
        border: `1px solid ${WC.botBorder}`,
        background: WC.page,
        boxSizing: 'border-box',
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: 10,
          top: '50%',
          transform: 'translateY(-50%)',
          width: SIDE_CONTROL,
          height: SIDE_CONTROL,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: WC.muted,
          lineHeight: 0,
        }}
      >
        {imageSlot ?? (
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            style={{ display: 'block' }}
          >
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
        )}
      </div>

      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onPaste={onPaste}
        placeholder={placeholder}
        disabled={loading}
        style={{
          display: 'block',
          boxSizing: 'border-box',
          width: '100%',
          height: '100%',
          margin: 0,
          border: 'none',
          outline: 'none',
          background: 'transparent',
          color: WC.botText,
          fontSize: 14,
          lineHeight: `${COMPOSER_HEIGHT}px`,
          paddingLeft: 10 + SIDE_CONTROL + SIDE_GAP,
          paddingRight: 10 + SIDE_CONTROL + SIDE_GAP,
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
        style={{
          position: 'absolute',
          right: 6,
          top: '50%',
          transform: 'translateY(-50%)',
          width: SIDE_CONTROL,
          height: SIDE_CONTROL,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: 'none',
          borderRadius: 9999,
          background: WC.indigo,
          color: WC.onPrimary,
          padding: 0,
          cursor: 'pointer',
          lineHeight: 0,
        }}
      >
        {loading ? (
          <span
            style={{
              display: 'block',
              width: 10,
              height: 10,
              borderRadius: 2,
              background: WC.onPrimary,
            }}
          />
        ) : (
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            style={{ display: 'block' }}
          >
            <path d="M5 12h14M13 6l6 6-6 6" />
          </svg>
        )}
      </button>
    </div>
  );
});
