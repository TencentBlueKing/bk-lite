'use client';

import React, { useMemo, useRef, useState } from 'react';
import { Dropdown, Input } from 'antd';

import { useFilterTemplateVariables } from '@/app/ops-analysis/context/filterTemplate';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import {
  filterDropdownType,
  listFilterTemplateVariables,
  listUnmatchedFilterTokens,
} from '@/app/ops-analysis/utils/filterTemplate';
import {
  listUnmatchedInteractionTokens,
  type InteractionVariable,
} from '@/app/ops-analysis/utils/interactionLink';

type FilterTokenTranslate = (
  key: string,
  defaultValue?: string,
  values?: Record<string, string | number>,
) => string;

interface FilterTokenInputProps {
  t: FilterTokenTranslate;
  value?: string;
  onChange?: (value: string) => void;
  id?: string;
  placeholder?: string;
  maxLength?: number;
  disabled?: boolean;
  allowClear?: boolean;
  className?: string;
  multiline?: boolean;
  rows?: number;
  autoSize?: { minRows?: number; maxRows?: number };
  definitions?: UnifiedFilterDefinition[];
  /** 传入后按下拉分组展示，不再从筛选定义推导变量。 */
  variables?: InteractionVariable[];
  hint?: string;
}

const NUMBER_PATTERN = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
const TIME_PATTERN = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?$/;

const scalarMenuType = (example?: string): 'number' | 'time' | 'text' | undefined => {
  const trimmed = example?.trim() ?? '';
  if (!trimmed) return undefined;
  if (NUMBER_PATTERN.test(trimmed)) return 'number';
  if (TIME_PATTERN.test(trimmed)) return 'time';
  return 'text';
};

/** 数据点和数据字段：数值是 number，时间是 time，其余是 text。看不出来就留空。 */
const dataMenuType = (token: string, example?: string): string | undefined => {
  const body = token.startsWith('$') && token.endsWith('$') ? token.slice(1, -1) : token;
  if (body === '__value.numeric') return 'number';
  if (body === '__value.time') return 'time';
  if (body === '__series.name' || body === '__value.text') return 'text';
  if (body.startsWith('__data.fields.') || body === '__value.raw') return scalarMenuType(example);
  return undefined;
};

const isEscapedDollar = (text: string, index: number) =>
  index > 0 && text[index - 1] === '\\';

/** 锚点 `$` 之后第一个未转义的 `$`，用来收尾当前变量。 */
const closingDollarIndex = (text: string, anchor: number) => {
  if (text[anchor] !== '$') return -1;
  for (let index = anchor + 1; index < text.length; index += 1) {
    if (text[index] !== '$' || isEscapedDollar(text, index)) continue;
    return index;
  }
  return -1;
};

const isImeKey = (event: React.KeyboardEvent) =>
  event.nativeEvent.isComposing || event.keyCode === 229;

const focusCaret = (field: HTMLDivElement | null, caret: number) => {
  const node = field?.querySelector('input, textarea');
  if (!(node instanceof HTMLInputElement) && !(node instanceof HTMLTextAreaElement)) return;
  node.focus();
  node.setSelectionRange(caret, caret);
};

export const FilterTokenInput: React.FC<FilterTokenInputProps> = ({
  t,
  value,
  onChange,
  id,
  placeholder,
  maxLength,
  disabled,
  allowClear,
  className,
  multiline = false,
  rows,
  autoSize,
  definitions,
  variables: variableSource,
  hint,
}) => {
  const contextDefinitions = useFilterTemplateVariables();
  const source = definitions ?? contextDefinitions;
  const filterVariables = useMemo(() => listFilterTemplateVariables(source), [source]);
  const menuItems = useMemo(() => {
    if (variableSource) {
      return variableSource.map((item) => ({
        key: `${item.group}:${item.token}`,
        token: item.token,
        label: item.label,
        group: item.group,
        example: item.example,
        valueType: item.valueType,
      }));
    }
    return filterVariables.map((item) => ({
      key: item.definition.id,
      token: item.token,
      label: item.definition.name || item.definition.key,
      group: '',
      example: undefined as string | undefined,
      valueType: filterDropdownType(item.definition.type),
    }));
  }, [filterVariables, variableSource]);
  const unmatchedTokens = useMemo(
    () => (
      variableSource
        ? listUnmatchedInteractionTokens(value ?? '', variableSource)
        : listUnmatchedFilterTokens(value ?? '', source)
    ),
    [source, value, variableSource],
  );
  const fieldRef = useRef<HTMLDivElement>(null);
  const anchorRef = useRef(0);
  const cursorRef = useRef(0);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const hintId = React.useId();

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return menuItems;
    return menuItems.filter((item) => {
      const typeName = item.valueType || dataMenuType(item.token, item.example) || '';
      const haystack = `${item.label} ${item.token} ${item.group} ${typeName}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [menuItems, query]);
  const currentIndex = Math.min(activeIndex, Math.max(filtered.length - 1, 0));
  const menuOpen = open && filtered.length > 0 && menuItems.length > 0;
  const hintText = hint === undefined
    ? t('dashboard.filterTokenHint', '输入 $ 引用全局筛选变量')
    : hint;
  const unmatchedMessage = unmatchedTokens.length
    ? t(
      'dashboard.filterTokenUnmatched',
      '{tokens} 未匹配到筛选项',
      {
        tokens: unmatchedTokens.join(t('dashboard.filterTokenSeparator', '、')),
      },
    )
    : '';

  const insertToken = (token: string) => {
    const current = value ?? '';
    const anchor = anchorRef.current;
    const end = Math.max(cursorRef.current, anchor + 1);
    const next = `${current.slice(0, anchor)}${token}${current.slice(end)}`;
    if (maxLength != null && next.length > maxLength) {
      setOpen(false);
      return;
    }
    onChange?.(next);
    setOpen(false);
    const caret = anchor + token.length;
    requestAnimationFrame(() => focusCaret(fieldRef.current, caret));
  };

  const handleValueChange = (next: string, cursor: number) => {
    const previous = value ?? '';
    cursorRef.current = cursor;
    onChange?.(next);
    const insertedAt = cursor - 1;
    const insertedDollar = insertedAt >= 0
      && next[insertedAt] === '$'
      && !isEscapedDollar(next, insertedAt)
      && previous[insertedAt] !== '$';
    const anchor = anchorRef.current;
    const closesCurrentToken = insertedDollar && insertedAt === closingDollarIndex(next, anchor);
    // 锚点后的第一个未转义 $ 只收尾。这里即使 open 还没刷新也要关掉，
    // 避免开头的 setOpen(true) 在组字结束后把菜单重新打开。
    if (closesCurrentToken) {
      setOpen(false);
      return;
    }

    if (open) {
      if (cursor <= anchor || next[anchor] !== '$') {
        setOpen(false);
        return;
      }
      setQuery(next.slice(anchor + 1, cursor));
      setActiveIndex(0);
      return;
    }
    if (!insertedDollar || menuItems.length === 0) return;
    anchorRef.current = insertedAt;
    setQuery('');
    setActiveIndex(0);
    setOpen(true);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement | HTMLInputElement>) => {
    if (!menuOpen || isImeKey(event)) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((currentIndex + 1) % filtered.length);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((currentIndex - 1 + filtered.length) % filtered.length);
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      event.stopPropagation();
      const selected = filtered[currentIndex];
      if (selected) insertToken(selected.token);
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
    }
  };

  const controlProps = {
    id,
    value: value ?? '',
    disabled,
    maxLength,
    placeholder,
    className,
    'aria-describedby': menuItems.length > 0 && hintText ? hintId : undefined,
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      handleValueChange(event.target.value, event.target.selectionStart ?? event.target.value.length);
    },
    onKeyDown: handleKeyDown,
    onBlur: () => setOpen(false),
  };

  const control = multiline ? (
    <Input.TextArea {...controlProps} rows={rows} autoSize={autoSize} />
  ) : (
    <Input {...controlProps} allowClear={allowClear} />
  );

  return (
    <div className="group flex w-full flex-col gap-1">
      <Dropdown
        open={menuOpen}
        trigger={[]}
        placement="bottomLeft"
        overlayStyle={{ zIndex: 2100 }}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) setOpen(false);
        }}
        popupRender={() => (
          <div
            role="listbox"
            className="max-h-64 min-w-52 overflow-x-hidden overflow-y-auto rounded-md border border-(--color-border-1) bg-(--color-bg-1) py-1 shadow-md"
          >
            {filtered.map((item, index) => {
              const previousGroup = index > 0 ? filtered[index - 1]?.group : '';
              const typeName = item.valueType || dataMenuType(item.token, item.example);
              const detail = typeName ? `${item.token} · ${typeName}` : item.token;
              return (
                <React.Fragment key={item.key}>
                  {item.group && item.group !== previousGroup ? (
                    <div className="px-3 py-1 text-[11px] font-medium text-(--color-text-3)">
                      {item.group}
                    </div>
                  ) : null}
                  <button
                    type="button"
                    role="option"
                    aria-selected={index === currentIndex}
                    className={`flex w-full min-w-0 cursor-pointer items-baseline justify-between gap-3 px-3 py-1.5 text-left text-xs text-(--color-text-1) ${
                      index === currentIndex ? 'bg-(--color-fill-2)' : 'hover:bg-(--color-fill-1)'
                    }`}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      insertToken(item.token);
                    }}
                    onMouseEnter={() => setActiveIndex(index)}
                  >
                    <span className="shrink-0">{item.label}</span>
                    <span
                      title={detail}
                      className="min-w-0 max-w-64 shrink truncate text-right text-[11px] text-(--color-text-3)"
                    >
                      {detail}
                    </span>
                  </button>
                </React.Fragment>
              );
            })}
          </div>
        )}
      >
        <div ref={fieldRef} className="w-full">{control}</div>
      </Dropdown>
      {menuItems.length > 0 && hintText ? (
        <span
          id={hintId}
          className="hidden text-xs leading-5 text-(--color-text-3) group-focus-within:block"
        >
          {hintText}
        </span>
      ) : null}
      {unmatchedMessage && (
        <span role="status" className="text-xs leading-5 text-(--color-warning)">
          {unmatchedMessage}
        </span>
      )}
    </div>
  );
};
