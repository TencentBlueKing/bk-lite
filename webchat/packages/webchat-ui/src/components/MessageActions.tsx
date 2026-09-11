import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { type MessageContent } from '@webchat/core';
import { getMessageCopyText } from '../messageContentActions';
import { WC } from '../chrome';

interface MessageActionsProps {
  messageId: string;
  messageContent: string | MessageContent[];
  isBot: boolean;
  isLastBotMessage?: boolean;
  showActions: boolean;
  onRegenerate?: (messageId: string) => void;
  onCopy?: (content: string) => void;
  onDelete?: (messageId: string) => void;
}

export const COPY_SUCCESS_LABEL = '已复制到剪贴板';
export const COPY_FEEDBACK_MS = 1600;
export const WEBCHAT_ROOT_ID = 'webchat-root';

type PortalAnchor = {
  closest?: (selector: string) => Element | null;
} | null;

/** Tailwind utilities are scoped to `#webchat-root`; never portal onto `document.body`. */
export function resolveWebchatPortalTarget(anchor: PortalAnchor): Element | null {
  if (typeof document === 'undefined') return null;
  return (
    document.getElementById(WEBCHAT_ROOT_ID) ??
    anchor?.closest?.(`#${WEBCHAT_ROOT_ID}`) ??
    null
  );
}

const iconBtnClass =
  'rounded p-1 text-[var(--color-text-3,#86909c)] transition-transform duration-150 hover:-translate-y-0.5 hover:bg-[var(--color-fill-2,#f4f6fa)] hover:text-[var(--color-text-1,#1d2129)]';

const Icon = ({
  children,
  color,
}: {
  children: React.ReactNode;
  color?: string;
}) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="12"
    height="12"
    viewBox="0 0 24 24"
    fill="none"
    stroke={color || 'currentColor'}
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {children}
  </svg>
);

const copyText = async (text: string): Promise<boolean> => {
  try {
    if (!navigator?.clipboard?.writeText) return false;
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
};

export const MessageActions: React.FC<MessageActionsProps> = ({
  messageId,
  messageContent,
  isBot,
  isLastBotMessage,
  showActions,
  onRegenerate,
  onCopy,
  onDelete,
}) => {
  const [copied, setCopied] = useState(false);
  const [tip, setTip] = useState<{ top: number; left: number } | null>(null);
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const copyBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    return () => {
      if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
    };
  }, []);

  const handleCopy = useCallback(async () => {
    const text = getMessageCopyText(messageContent);
    const ok = await copyText(text);
    if (!ok) return;
    onCopy?.(text);
    setCopied(true);
    const rect = copyBtnRef.current?.getBoundingClientRect();
    setTip(
      rect
        ? { top: rect.top - 8, left: rect.left + rect.width / 2 }
        : null
    );
    if (copiedTimerRef.current) clearTimeout(copiedTimerRef.current);
    copiedTimerRef.current = setTimeout(() => {
      setCopied(false);
      setTip(null);
    }, COPY_FEEDBACK_MS);
  }, [messageContent, onCopy]);

  const copyLabel = copied ? COPY_SUCCESS_LABEL : '复制';
  const visible = showActions || copied;
  const portalTarget =
    copied && tip ? resolveWebchatPortalTarget(copyBtnRef.current) : null;

  return (
    <div
      className={`flex h-6 items-center gap-0.5 px-2 text-xs transition-all duration-150 ${
        isBot ? '' : 'justify-end'
      } ${visible ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-1 opacity-0'}`}
    >
      {isLastBotMessage && (
        <button
          type="button"
          onClick={() => onRegenerate?.(messageId)}
          className={iconBtnClass}
          title="重新生成"
        >
          <Icon>
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
          </Icon>
        </button>
      )}
      <button
        ref={copyBtnRef}
        type="button"
        onClick={() => {
          void handleCopy();
        }}
        className={iconBtnClass}
        title={copied ? undefined : '复制'}
        aria-label={copyLabel}
      >
        {copied ? (
          <Icon color={WC.success}>
            <path d="M20 6 9 17l-5-5" />
          </Icon>
        ) : (
          <Icon>
            <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
            <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
          </Icon>
        )}
      </button>
      <button
        type="button"
        onClick={() => onDelete?.(messageId)}
        className={iconBtnClass}
        title="删除"
      >
        <Icon>
          <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
        </Icon>
      </button>
      {copied && tip && portalTarget
        ? createPortal(
            <div
              role="status"
              style={{
                position: 'fixed',
                top: tip.top,
                left: tip.left,
                transform: 'translate(-50%, -100%)',
                zIndex: 2100,
                maxWidth: 240,
                padding: '6px 10px',
                borderRadius: 6,
                fontSize: 12,
                lineHeight: '18px',
                pointerEvents: 'none',
                background: WC.botText,
                color: WC.white,
                boxShadow: WC.shadow,
              }}
            >
              {COPY_SUCCESS_LABEL}
            </div>,
            portalTarget
          )
        : null}
    </div>
  );
};
