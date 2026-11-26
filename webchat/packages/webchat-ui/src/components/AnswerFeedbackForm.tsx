import { useId, useLayoutEffect, useRef, useState } from 'react';
import { answerFeedbackReasons, type AnswerFeedback, type AnswerFeedbackDetail, type FeedbackTag } from '@webchat/core';
import { useTranslator } from '../useTranslator';

interface Props {
  rating: Exclude<AnswerFeedback, null>;
  initial?: AnswerFeedbackDetail;
  saving: boolean;
  failed: boolean;
  onSave: (detail: AnswerFeedbackDetail) => void;
  onClose: () => void;
}

export function AnswerFeedbackForm({ rating, initial, saving, failed, onSave, onClose }: Props) {
  const t = useTranslator();
  const headingId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [selected, setSelected] = useState<FeedbackTag[]>(initial?.reasons ?? []);
  const [comment, setComment] = useState(initial?.comment ?? '');
  const tags: readonly FeedbackTag[] = answerFeedbackReasons[rating];
  const legacy = initial?.reasons.filter(tag => !tags.includes(tag)) ?? [];
  const choices = [...tags, ...legacy];
  const trimmed = comment.trim();
  const changed = trimmed !== (initial?.comment ?? '') || selected.length !== (initial?.reasons.length ?? 0)
    || selected.some(tag => !initial?.reasons.includes(tag));

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    inputRef.current?.focus({ preventScroll: true });
    return () => dialog?.close();
  }, []);

  return (
    <dialog ref={dialogRef} aria-labelledby={headingId}
      className="webchat-feedback-dialog m-auto box-border max-h-[calc(100dvh-32px)] w-[600px] max-w-[calc(100vw-32px)] overflow-auto rounded-[20px] border-0 bg-[var(--color-bg,#fff)] p-5 text-[var(--color-text-1,#1d2129)] shadow-lg"
      onKeyDown={event => { if (event.key === 'Escape') event.stopPropagation(); }}
      onCancel={event => { event.preventDefault(); if (!saving) onClose(); }}
      onClick={event => {
        if (saving || event.target !== event.currentTarget) return;
        const rect = event.currentTarget.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
      }}
    >
      <form aria-labelledby={headingId} onSubmit={event => {
        event.preventDefault();
        if (!saving && changed) onSave({ reasons: selected, comment: trimmed });
      }}>
        <div className="mb-5 flex items-start justify-between">
          <h2 id={headingId} className="m-0 text-xl font-semibold leading-7">{t('feedback.heading', '提交反馈')}</h2>
          <button type="button" aria-label={t('chat.close', '关闭')} disabled={saving} onClick={onClose}
            className="inline-flex h-6 w-6 items-center justify-center rounded-md border-0 bg-transparent text-[var(--color-text-2,#4e5969)] hover:bg-[var(--color-fill-2,#f4f6fa)]">
            <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="m4 4 8 8m0-8-8 8" /></svg>
          </button>
        </div>
        <div className="flex flex-col gap-2">
          {[choices.slice(0, 3), choices.slice(3, 6), choices.slice(6)].filter(row => row.length).map(row => (
            <div key={row[0]} className="flex flex-wrap gap-2">
              {row.map(tag => (
                <button key={tag} type="button" disabled={saving} aria-pressed={selected.includes(tag)} aria-label={t(`feedback.${tag}`)}
                  onClick={() => setSelected(prev => prev.includes(tag) ? prev.filter(item => item !== tag) : [...prev, tag])}
                  className="inline-flex min-h-8 items-center gap-1 rounded-full border border-solid border-[var(--color-border-1,#e4e4e4)] bg-transparent px-3 py-1 text-sm font-medium text-inherit hover:bg-[var(--color-fill-2,#f4f6fa)] aria-pressed:border-current">
                  <span aria-hidden="true">{selected.includes(tag) ? '✓' : '+'}</span>{t(`feedback.${tag}`)}
                </button>
              ))}
            </div>
          ))}
        </div>
        <textarea ref={inputRef} aria-label={t('feedback.comment')} placeholder={t('feedback.comment')} maxLength={500}
          value={comment} disabled={saving} onChange={event => setComment(event.target.value)}
          className="mt-3 block h-28 w-full resize-y rounded-lg border border-solid border-[var(--color-border-1,#ddd)] bg-transparent p-2.5 text-sm text-inherit focus:border-[var(--color-primary,#155aef)] focus:outline-none box-border"
        />
        <p className="mb-0 mt-3 text-[13px] text-[var(--color-text-3,#777)]">{t('feedback.notice')}</p>
        {failed && <p role="alert" className="mb-0 mt-2 text-sm text-[var(--color-fail,#c53d42)]">{t('message.feedbackError')}</p>}
        <div className="mt-5 flex justify-end">
          <button type="submit" disabled={!changed || saving}
            className="h-8 min-w-[78px] rounded-[10px] border-0 bg-[var(--color-text-1,#222)] px-4 text-sm font-medium text-[var(--color-bg,#fff)] disabled:opacity-35">
            {t('feedback.save', '提交')}
          </button>
        </div>
      </form>
    </dialog>
  );
}
