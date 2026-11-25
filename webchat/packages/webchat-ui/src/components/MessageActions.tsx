import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { type AnswerFeedbackDetail, type AnswerFeedback, type MessageContent } from '@webchat/core';
import { MessageActionMenu } from './MessageActionMenu';
import { AnswerFeedbackForm } from './AnswerFeedbackForm';
import { getMessageCopyText } from '../messageContentActions';
import { WC } from '../chrome';
import { useTranslator } from '../useTranslator';

interface MessageActionsProps {
  messageId: string;
  messageContent: string | MessageContent[];
  isBot: boolean;
  feedback?: AnswerFeedback;
  feedbackDetail?: AnswerFeedbackDetail;
  onFeedback?: (value: AnswerFeedback, detail?: AnswerFeedbackDetail) => Promise<void>;
  isLastBotMessage?: boolean;
  showActions: boolean;
  onRegenerate?: (messageId: string) => void;
  onCopy?: (content: string) => void;
  onDelete?: (messageId: string) => void;
}

export const COPY_SUCCESS_LABEL_KEY = 'message.copied';
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
  'inline-flex h-7 w-7 shrink-0 cursor-pointer appearance-none items-center justify-center rounded-md border-0 bg-transparent p-0 ' +
  'text-[var(--color-text-3,#75808c)] hover:bg-[var(--color-fill-2,#f4f6fa)] hover:text-[var(--color-text-1,#1d2129)] ' +
  'aria-pressed:text-[var(--color-text-1,#1d2129)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 ' +
  'focus-visible:outline-[var(--color-primary,#155aef)] [@media(pointer:coarse)]:h-9 [@media(pointer:coarse)]:w-9';

const Icon = ({
  children,
  color,
}: {
  children: React.ReactNode;
  color?: string;
}) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke={color || 'currentColor'}
    strokeWidth="1.65"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {children}
  </svg>
);

const menuItemClass = 'flex h-7 w-full items-center gap-2 whitespace-nowrap rounded-lg border-0 bg-transparent px-2.5 text-left text-sm text-inherit hover:bg-[var(--color-fill-2,#f4f6fa)] focus-visible:bg-[var(--color-fill-2,#f4f6fa)] focus-visible:outline-none';

function ThumbIcon({ rating, selected }: { rating?: AnswerFeedback; selected: boolean }) {
  const thumb = <path d="M7 10H3v11h4zM9.5 20V10l4-7c1.9-.2 2.8 1.4 2.4 3.2l-.7 3.5h4c1.6 0 2.4 1.3 2 2.8l-1.5 6a2.4 2.4 0 0 1-2.3 1.8h-6z" />;
  return (
    <Icon>
      {rating ? <g fill={selected ? 'currentColor' : 'none'} transform={rating === 'dislike' ? 'rotate(180 12 12)' : undefined}>{thumb}</g> : <>
        <g transform="translate(0 0) scale(.65)" strokeWidth="2">{thumb}</g>
        <g transform="translate(24 24) rotate(180) scale(.65)" strokeWidth="2">{thumb}</g>
      </>}
    </Icon>
  );
}

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
  feedback,
  feedbackDetail,
  onFeedback,
  isLastBotMessage,
  showActions,
  onRegenerate,
  onCopy,
  onDelete,
}) => {
  const t = useTranslator();
  const [savingFeedback, setSavingFeedback] = useState(false);
  const [feedbackError, setFeedbackError] = useState(false);
  const savingRef = useRef(false);
  const [surface, setSurface] = useState<'rating' | 'more' | 'form' | null>(null);
  const ratingRef = useRef<HTMLButtonElement>(null);
  const moreRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);
  const dismiss = useCallback(() => { setSurface(null); setFeedbackError(false); }, []);
  const closeForm = () => { returnFocus.current = true; dismiss(); };
  useLayoutEffect(() => {
    if (!surface && returnFocus.current) {
      returnFocus.current = false;
      ratingRef.current?.focus();
    }
  }, [surface]);
  const submitFeedback = async (next: AnswerFeedback, detail?: AnswerFeedbackDetail) => {
    if (!onFeedback || savingRef.current) return;
    savingRef.current = true;
    setSavingFeedback(true);
    setFeedbackError(false);
    try {
      await onFeedback(next, detail);
      if (next && !detail) setSurface(current => current === 'rating' ? 'form' : current);
      else closeForm();
    } catch {
      setFeedbackError(true);
    } finally {
      savingRef.current = false;
      setSavingFeedback(false);
    }
  };
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

  const copySuccessLabel = t(COPY_SUCCESS_LABEL_KEY, '已复制到剪贴板');
  const copyLabel = copied ? copySuccessLabel : t('message.copy', '复制');
  const canVote = isBot && Boolean(onFeedback);
  const visible = surface || showActions || copied || feedbackError || (canVote && (isLastBotMessage || feedback || savingFeedback));
  const toggle = (menu: 'rating' | 'more') => {
    setFeedbackError(false);
    setSurface(current => current === menu ? null : menu);
  };
  const portalTarget =
    copied && tip ? resolveWebchatPortalTarget(copyBtnRef.current) : null;

  return (
    <>
    <div
      className={`flex min-h-7 items-center gap-0.5 text-xs transition-opacity duration-150 motion-reduce:transition-none
        focus-within:pointer-events-auto focus-within:opacity-100 [@media(hover:none)]:pointer-events-auto [@media(hover:none)]:opacity-100
        ${isBot ? '-ml-1.5 mt-1' : 'justify-end'} ${visible ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
    >
      <button
        ref={copyBtnRef}
        type="button"
        onClick={() => {
          void handleCopy();
        }}
        className={iconBtnClass}
        title={copied ? undefined : t('message.copy', '复制')}
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
      {canVote && (
        <>
          <button type="button" ref={ratingRef} aria-label={t('feedback.rate')} title={t('feedback.rate')}
            aria-haspopup="menu" aria-expanded={surface === 'rating'} onClick={() => toggle('rating')}
            className={`${iconBtnClass} aria-expanded:bg-[var(--color-fill-2,#f4f6fa)]`}>
            <ThumbIcon rating={feedback} selected={!!feedback} />
          </button>
          {surface === 'rating' && (
            <MessageActionMenu anchor={ratingRef} label={t('feedback.rate')} onClose={dismiss}>
              {(['like', 'dislike'] as const).map(value => {
                const label = t(value === 'like' ? 'feedback.good' : 'feedback.bad');
                const selected = value === feedback;
                return <button key={value} type="button" role="menuitemradio" aria-checked={selected} aria-label={label}
                  title={selected ? t('message.undoFeedback') : label} disabled={savingFeedback}
                  onClick={() => void submitFeedback(selected ? null : value)} className={menuItemClass}>
                  <ThumbIcon rating={value} selected={selected} />{label}{selected && <span aria-hidden="true">✓</span>}
                </button>;
              })}
              {feedbackError && <span role="alert">{t('message.feedbackError')}</span>}
            </MessageActionMenu>
          )}
          <button type="button" ref={moreRef} aria-label={t('feedback.more')} title={t('feedback.more')}
            aria-haspopup="menu" aria-expanded={surface === 'more'} onClick={() => toggle('more')}
            className={iconBtnClass}>
            <Icon>{[4, 12, 20].map(cx => <circle key={cx} cx={cx} cy="12" r="1.6" fill="currentColor" stroke="none" />)}</Icon>
          </button>
          {surface === 'more' && (
            <MessageActionMenu anchor={moreRef} label={t('feedback.more')} onClose={dismiss}>
              {feedback && <button type="button" role="menuitem" className={menuItemClass}
                onClick={() => setSurface('form')}>{t('feedback.edit')}</button>}
              {isLastBotMessage && <button type="button" role="menuitem" className={menuItemClass}
                onClick={() => { dismiss(); onRegenerate?.(messageId); }}>{t('message.regenerate')}</button>}
              <button type="button" role="menuitem" className={menuItemClass}
                onClick={() => { dismiss(); onDelete?.(messageId); }}>{t('message.delete')}</button>
            </MessageActionMenu>
          )}
        </>
      )}
      {!canVote && isLastBotMessage && (
        <button
          type="button"
          onClick={() => onRegenerate?.(messageId)}
          className={iconBtnClass}
          title={t('message.regenerate', '重新生成')}
        >
          <Icon>
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
          </Icon>
        </button>
      )}
      {!canVote && <button
        type="button"
        onClick={() => onDelete?.(messageId)}
        className={iconBtnClass}
        title={t('message.delete', '删除')}
      >
        <Icon>
          <path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
        </Icon>
      </button>}
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
              {copySuccessLabel}
            </div>,
            portalTarget
          )
        : null}
    </div>
    {surface === 'form' && canVote && feedback && (
      <AnswerFeedbackForm rating={feedback} initial={feedbackDetail} saving={savingFeedback} failed={feedbackError}
        onSave={detail => void submitFeedback(feedback, detail)} onClose={closeForm} />
    )}
    </>
  );
};
