'use client';

import { Input } from 'antd';
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';

import { useTranslation } from '@/utils/i18n';

import type { DataReferenceOption } from '../lib/data-references';

export const WORKFLOW_REFERENCE_MIME = 'application/x-bklite-workflow-reference';

/** Match `$` / `$partial` / `${partial` just before the caret for autocomplete. */
export function matchTemplateTrigger(text: string, caret: number) {
  const before = text.slice(0, Math.max(0, Math.min(caret, text.length)));
  const match = /\$(\{?[^\s{}]*)$/.exec(before);
  if (!match) return null;
  return {
    start: match.index,
    query: match[1] || '',
  };
}

function insertText(source: string, start: number, end: number, insertion: string) {
  const safeStart = Math.max(0, Math.min(start, source.length));
  const safeEnd = Math.max(safeStart, Math.min(end, source.length));
  return {
    next: `${source.slice(0, safeStart)}${insertion}${source.slice(safeEnd)}`,
    caret: safeStart + insertion.length,
  };
}

function filterReferences(references: DataReferenceOption[], query: string) {
  const needle = query.replace(/^\{/, '').toLowerCase();
  if (!needle) return references;
  return references.filter((item) => {
    const haystack = `${item.displayName || ''} ${item.label} ${item.value} ${item.path || ''}`.toLowerCase();
    return haystack.includes(needle);
  });
}

const SUGGESTION_MENU_MAX = 256;

/** Prefer below the field; flip above when bottom space is tight. */
export function computeSuggestionMenuPosition(rect: DOMRect, viewportHeight = typeof window === 'undefined' ? 800 : window.innerHeight) {
  const gap = 4;
  const spaceBelow = Math.max(0, viewportHeight - rect.bottom - gap);
  const spaceAbove = Math.max(0, rect.top - gap);
  const placeAbove = spaceBelow < 160 && spaceAbove > spaceBelow;
  const maxHeight = Math.max(120, Math.min(SUGGESTION_MENU_MAX, placeAbove ? spaceAbove : spaceBelow || SUGGESTION_MENU_MAX));
  return {
    top: placeAbove ? Math.max(gap, rect.top - gap - maxHeight) : rect.bottom + gap,
    left: rect.left,
    width: Math.max(rect.width, 280),
    maxHeight,
    placement: placeAbove ? 'top' as const : 'bottom' as const,
  };
}

export function WorkflowTemplateTextField({
  value,
  references,
  rows = 1,
  disabled = false,
  placeholder,
  isDragOver = false,
  onChange,
  onDragStateChange,
  onRejectDrop,
}: {
  value: string;
  references: DataReferenceOption[];
  rows?: number;
  disabled?: boolean;
  placeholder?: string;
  isDragOver?: boolean;
  onChange: (value: string) => void;
  onDragStateChange?: (state: 'accept' | 'reject' | null) => void;
  onRejectDrop?: (expression: string) => void;
}) {
  const { t } = useTranslation();
  const listId = useId();
  const selectionRef = useRef({ start: value.length, end: value.length });
  const inputRef = useRef<HTMLTextAreaElement | HTMLInputElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [trigger, setTrigger] = useState<{ start: number; query: string } | null>(null);
  const [menuPos, setMenuPos] = useState<ReturnType<typeof computeSuggestionMenuPosition> | null>(null);
  const [localDragOver, setLocalDragOver] = useState(false);
  const text = value ?? '';
  const allowed = new Set(references.map((item) => item.value));
  const showDragOver = isDragOver || localDragOver;
  const filtered = useMemo(
    () => filterReferences(references, trigger?.query || ''),
    [references, trigger?.query],
  );

  const setDragState = (state: 'accept' | 'reject' | null) => {
    setLocalDragOver(state === 'accept');
    onDragStateChange?.(state);
  };

  const updateMenuPosition = () => {
    if (!inputRef.current) {
      setMenuPos(null);
      return;
    }
    setMenuPos(computeSuggestionMenuPosition(inputRef.current.getBoundingClientRect()));
  };

  const syncSelection = (target: EventTarget | null) => {
    if (!(target instanceof HTMLTextAreaElement) && !(target instanceof HTMLInputElement)) return;
    selectionRef.current = { start: target.selectionStart ?? 0, end: target.selectionEnd ?? 0 };
  };

  const refreshTrigger = (nextText: string, caret: number) => {
    const nextTrigger = matchTemplateTrigger(nextText, caret);
    setTrigger(nextTrigger);
    setOpen(Boolean(nextTrigger) && !disabled);
    setActiveIndex(0);
  };

  const applyInsertion = (expression: string, replaceStart?: number, replaceEnd?: number) => {
    const start = replaceStart ?? selectionRef.current.start;
    const end = replaceEnd ?? selectionRef.current.end;
    const { next, caret } = insertText(text, start, end, expression);
    onChange(next);
    selectionRef.current = { start: caret, end: caret };
    setOpen(false);
    setTrigger(null);
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(caret, caret);
    });
  };

  const pickOption = (item: DataReferenceOption) => {
    if (!trigger) {
      applyInsertion(item.value);
      return;
    }
    applyInsertion(item.value, trigger.start, selectionRef.current.start);
  };

  const resolveExpression = (event: DragEvent<HTMLDivElement>) => {
    const types = Array.from(event.dataTransfer.types || []);
    const expression = event.dataTransfer.getData(WORKFLOW_REFERENCE_MIME)
      || event.dataTransfer.getData('text/plain');
    return { types, expression };
  };

  const allowDrop = (event: DragEvent<HTMLDivElement>) => {
    if (disabled) return;
    const { types, expression } = resolveExpression(event);
    if (!types.includes(WORKFLOW_REFERENCE_MIME)) return;
    event.preventDefault();
    if (expression && !allowed.has(expression)) {
      event.dataTransfer.dropEffect = 'none';
      setDragState('reject');
      return;
    }
    event.dataTransfer.dropEffect = 'copy';
    setDragState('accept');
  };

  const acceptDrop = (event: DragEvent<HTMLDivElement>) => {
    if (disabled) return;
    const { expression } = resolveExpression(event);
    setDragState(null);
    if (!expression) return;
    event.preventDefault();
    if (!allowed.has(expression)) {
      onRejectDrop?.(expression);
      return;
    }
    applyInsertion(expression);
  };

  useLayoutEffect(() => {
    if (!open) {
      setMenuPos(null);
      return;
    }
    updateMenuPosition();
  }, [open, text, filtered.length]);

  useEffect(() => {
    if (!open) return undefined;
    const onViewportChange = (event: Event) => {
      // 列表自身滚动不应关闭；外侧滚动/缩放时只重算位置。
      if (event.type === 'scroll' && menuRef.current?.contains(event.target as Node)) return;
      updateMenuPosition();
    };
    window.addEventListener('scroll', onViewportChange, true);
    window.addEventListener('resize', onViewportChange);
    return () => {
      window.removeEventListener('scroll', onViewportChange, true);
      window.removeEventListener('resize', onViewportChange);
    };
  }, [open]);

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement | HTMLInputElement>) => {
    if (!open || !filtered.length) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % filtered.length);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + filtered.length) % filtered.length);
      return;
    }
    if (event.key === 'Enter' || event.key === 'Tab') {
      event.preventDefault();
      pickOption(filtered[activeIndex] || filtered[0]);
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
    }
  };

  const sharedProps = {
    disabled,
    value: text,
    placeholder: placeholder || t('workflowOrchestration.editor.templateTextPlaceholder', '输入文本，键入 $ 选择上游字段，或从左侧拖入'),
    onKeyDown,
    onKeyUp: (event: KeyboardEvent<HTMLTextAreaElement | HTMLInputElement>) => {
      syncSelection(event.target);
      const target = event.target as HTMLTextAreaElement | HTMLInputElement;
      refreshTrigger(target.value, target.selectionStart ?? target.value.length);
    },
    onClick: (event: { target: EventTarget }) => {
      syncSelection(event.target);
      const target = event.target as HTMLTextAreaElement | HTMLInputElement;
      refreshTrigger(target.value, target.selectionStart ?? target.value.length);
    },
    onBlur: () => {
      // Delay so option click can run first.
      window.setTimeout(() => setOpen(false), 120);
    },
    onChange: (event: { target: HTMLTextAreaElement | HTMLInputElement }) => {
      const next = event.target.value;
      const caret = event.target.selectionStart ?? next.length;
      selectionRef.current = { start: caret, end: event.target.selectionEnd ?? caret };
      onChange(next);
      refreshTrigger(next, caret);
    },
  };

  const menu = open && menuPos && typeof document !== 'undefined'
    ? createPortal(
      <div
        ref={menuRef}
        id={listId}
        role="listbox"
        data-testid="workflow-template-suggestions"
        data-placement={menuPos.placement}
        className="fixed z-[1100] overflow-auto rounded-md border border-[var(--color-border-1)] bg-[var(--color-bg)] py-1 shadow-lg"
        style={{ top: menuPos.top, left: menuPos.left, width: menuPos.width, maxHeight: menuPos.maxHeight }}
        onMouseDown={(event) => event.preventDefault()}
      >
        {filtered.length ? filtered.map((item, index) => (
          <button
            key={item.value}
            type="button"
            role="option"
            aria-selected={index === activeIndex}
            className={`flex w-full flex-col gap-0.5 px-3 py-1.5 text-left hover:bg-[var(--color-fill-2)] ${index === activeIndex ? 'bg-[var(--color-fill-2)]' : ''}`}
            onMouseEnter={() => setActiveIndex(index)}
            onClick={() => pickOption(item)}
          >
            <span className="truncate text-xs text-[var(--color-text-1)]">{item.displayName || item.label}</span>
            <span className="truncate font-mono text-[11px] text-[var(--color-text-4)]">{item.value}</span>
          </button>
        )) : (
          <div className="px-3 py-2 text-xs text-[var(--color-text-3)]">
            {t('workflowOrchestration.editor.noMatchingReferences', '没有匹配的上游字段')}
          </div>
        )}
      </div>,
      document.body,
    )
    : null;

  return (
    <div
      data-testid="workflow-reference-dropzone"
      className={`w-full rounded-md outline-none transition focus-within:ring-2 focus-within:ring-[var(--color-primary)]/15 ${showDragOver ? 'ring-2 ring-[var(--color-primary)]/35' : ''}`}
      onDragEnter={allowDrop}
      onDragLeave={() => setDragState(null)}
      onDragOverCapture={allowDrop}
      onDropCapture={acceptDrop}
    >
      {rows > 1 ? (
        <Input.TextArea
          {...sharedProps}
          rows={rows}
          ref={(node) => { inputRef.current = node?.resizableTextArea?.textArea ?? null; }}
        />
      ) : (
        <Input
          {...sharedProps}
          className="w-full"
          ref={(node) => { inputRef.current = node?.input || null; }}
        />
      )}
      {menu}
    </div>
  );
}
