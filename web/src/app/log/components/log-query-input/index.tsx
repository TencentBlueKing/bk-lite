'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from 'react';
import { AutoComplete, Input } from 'antd';
import type { InputProps, InputRef } from 'antd';
import type { DefaultOptionType } from 'antd/es/select';
import useIntegrationApi from '@/app/log/api/integration';
import { useTranslation } from '@/utils/i18n';

interface FieldValueItem {
  value: string;
  hits: number;
}

interface QueryContext {
  type: 'field' | 'value';
  prefix: string;
  fieldName: string;
  startPos: number;
  endPos: number;
}

interface QueryOption extends DefaultOptionType {
  type?: 'field' | 'value';
}

export type LogQueryTimeRange =
  | { mode: 'relative'; minutes: number }
  | { mode: 'absolute'; start: number; end: number };

export interface LogQueryInputProps
  extends Omit<
    InputProps,
    'value' | 'defaultValue' | 'onChange' | 'onPressEnter'
  > {
  value?: string;
  onChange?: (value: string) => void;
  onPressEnter?: () => void;
  availableFields: string[];
  logGroups: React.Key[];
  timeRange?: LogQueryTimeRange;
  fieldsLoading?: boolean;
}

const DEFAULT_TIME_RANGE: LogQueryTimeRange = {
  mode: 'relative',
  minutes: 15
};
const FIELD_VALUE_LIMIT = 50;
const FIELD_VALUE_DEBOUNCE_MS = 300;
const HIDDEN_QUERY_FIELDS = new Set([
  '@timestamp',
  '_msg',
  '_time',
  '_stream',
  '_stream_id',
  '*'
]);
const SIMPLE_LOGSQL_FIELD = /^[A-Za-z_][A-Za-z0-9_.]*$/;

const quoteLogsqlValue = (value: string) => {
  const escaped = value
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r');
  return `"${escaped}"`;
};

const quoteLogsqlField = (field: string) =>
  SIMPLE_LOGSQL_FIELD.test(field) ? field : quoteLogsqlValue(field);

const unwrapLogsqlField = (field: string) => {
  if (field.length >= 2 && field.startsWith('"') && field.endsWith('"')) {
    return field.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, '\\');
  }
  return field;
};

const findSegmentBounds = (inputValue: string, cursorPos: number) => {
  let segmentStart = 0;
  let quoted = false;
  let escaped = false;

  for (let index = 0; index < cursorPos; index += 1) {
    const char = inputValue[index];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (char === '\\') {
      escaped = true;
      continue;
    }
    if (char === '"') {
      quoted = !quoted;
      continue;
    }
    if (/\s/.test(char) && !quoted) {
      segmentStart = index + 1;
    }
  }

  let segmentEnd = inputValue.length;
  escaped = false;
  for (let index = cursorPos; index < inputValue.length; index += 1) {
    const char = inputValue[index];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (char === '\\') {
      escaped = true;
      continue;
    }
    if (char === '"') {
      quoted = !quoted;
      continue;
    }
    if (/\s/.test(char) && !quoted) {
      segmentEnd = index;
      break;
    }
  }

  return { segmentStart, segmentEnd };
};

const parseQueryContext = (
  inputValue: string,
  cursorPosition?: number | null
): QueryContext => {
  const cursorPos = Math.max(
    0,
    Math.min(cursorPosition ?? inputValue.length, inputValue.length)
  );
  const { segmentStart, segmentEnd } = findSegmentBounds(
    inputValue,
    cursorPos
  );
  const currentSegment = inputValue.slice(segmentStart, segmentEnd);
  const positionInSegment = cursorPos - segmentStart;
  const colonIndex = currentSegment.indexOf(':');

  if (colonIndex === -1 || positionInSegment <= colonIndex) {
    return {
      type: 'field',
      prefix: currentSegment.slice(0, positionInSegment),
      fieldName: '',
      startPos: segmentStart,
      endPos:
        colonIndex === -1 ? segmentEnd : segmentStart + Math.max(colonIndex, 0)
    };
  }

  return {
    type: 'value',
    prefix: currentSegment.slice(colonIndex + 1, positionInSegment),
    fieldName: unwrapLogsqlField(currentSegment.slice(0, colonIndex)),
    startPos: segmentStart + colonIndex + 1,
    endPos: segmentEnd
  };
};

const getTimeRangeParams = (timeRange: LogQueryTimeRange) => {
  if (timeRange.mode === 'absolute') {
    return {
      start_time: new Date(timeRange.start).toISOString(),
      end_time: new Date(timeRange.end).toISOString()
    };
  }
  const end = Date.now();
  const start = end - timeRange.minutes * 60 * 1000;
  return {
    start_time: new Date(start).toISOString(),
    end_time: new Date(end).toISOString()
  };
};

const LogQueryInput: React.FC<LogQueryInputProps> = React.memo(
  ({
    value,
    onChange,
    onPressEnter,
    availableFields,
    logGroups,
    timeRange = DEFAULT_TIME_RANGE,
    fieldsLoading = false,
    placeholder,
    className,
    style,
    disabled = false,
    allowClear = false,
    addonAfter,
    ...inputProps
  }) => {
    const { t } = useTranslation();
    const { getFieldValues } = useIntegrationApi();
    const inputRef = useRef<InputRef>(null);
    const realCursorPosRef = useRef(0);
    const refreshSuggestionsRef = useRef<
      (inputValue: string, cursorPosition?: number | null) => void
        >(() => undefined);
    const valueRef = useRef(value || '');
    const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
      null
    );
    const requestControllerRef = useRef<AbortController | null>(null);
    const requestVersionRef = useRef(0);
    const cacheRef = useRef<{
      scopeKey: string;
      fieldName: string;
      values: FieldValueItem[];
    } | null>(null);
    const [uncontrolledValue, setUncontrolledValue] = useState(value || '');
    const [options, setOptions] = useState<QueryOption[]>([]);
    const [dropdownOpen, setDropdownOpen] = useState(false);
    const resolvedValue = value === undefined ? uncontrolledValue : value;
    const resolvedPlaceholder =
      placeholder || t('log.search.smartSearchPlaceHolder');
    const normalizedGroups = useMemo(
      () => logGroups.map(String).sort(),
      [logGroups]
    );
    const scopeKey = useMemo(
      () => JSON.stringify([normalizedGroups, timeRange]),
      [normalizedGroups, timeRange]
    );

    useEffect(() => {
      valueRef.current = resolvedValue;
    }, [resolvedValue]);

    const clearPendingRequest = useCallback(() => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
      requestControllerRef.current?.abort();
      requestControllerRef.current = null;
      requestVersionRef.current += 1;
    }, []);

    const closeDropdown = useCallback(() => {
      setOptions([]);
      setDropdownOpen(false);
    }, []);

    useEffect(() => {
      clearPendingRequest();
      cacheRef.current = null;
      closeDropdown();
    }, [scopeKey, clearPendingRequest, closeDropdown]);

    useEffect(
      () => () => {
        clearPendingRequest();
      },
      [clearPendingRequest]
    );

    const commitValue = useCallback(
      (nextValue: string) => {
        valueRef.current = nextValue;
        setUncontrolledValue(nextValue);
        onChange?.(nextValue);
      },
      [onChange]
    );

    const messageOption = useCallback(
      (key: string): QueryOption[] => [
        {
          value: key,
          label: (
            <div className="flex items-center justify-center text-[var(--color-text-3)]">
              {t(key)}
            </div>
          ),
          disabled: true
        }
      ],
      [t]
    );

    const showValueOptions = useCallback(
      (values: FieldValueItem[], prefix: string) => {
        const normalizedPrefix = prefix.replace(/^"/, '').toLowerCase();
        const filteredValues = values
          .filter((item) => {
            if (!normalizedPrefix) return true;
            const normalizedValue = item.value.toLowerCase();
            return (
              normalizedValue.startsWith(normalizedPrefix) ||
              normalizedValue.includes(normalizedPrefix) ||
              normalizedValue
                .split(/\s+/)
                .some((word) => word.startsWith(normalizedPrefix))
            );
          })
          .sort((left, right) => {
            const leftValue = left.value.toLowerCase();
            const rightValue = right.value.toLowerCase();
            const leftStarts = leftValue.startsWith(normalizedPrefix);
            const rightStarts = rightValue.startsWith(normalizedPrefix);
            if (leftStarts !== rightStarts) return leftStarts ? -1 : 1;
            if (left.hits !== right.hits) return right.hits - left.hits;
            return left.value.length - right.value.length;
          });

        if (!filteredValues.length) {
          setOptions(messageOption('log.search.noMatchValues'));
          setDropdownOpen(true);
          return;
        }

        setOptions(
          filteredValues.map((item) => ({
            value: item.value,
            type: 'value',
            title: item.value,
            label: (
              <div className="flex max-w-full items-center gap-2">
                <span
                  className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap"
                  title={item.value}
                >
                  {item.value}
                </span>
                <span className="shrink-0 text-xs text-[var(--color-text-3)]">
                  {item.hits} hits
                </span>
              </div>
            )
          }))
        );
        setDropdownOpen(true);
      },
      [messageOption]
    );

    const loadFieldValues = useCallback(
      async (fieldName: string) => {
        if (!normalizedGroups.length || !availableFields.includes(fieldName)) {
          closeDropdown();
          return;
        }

        const requestVersion = requestVersionRef.current + 1;
        requestVersionRef.current = requestVersion;
        requestControllerRef.current?.abort();
        const controller = new AbortController();
        requestControllerRef.current = controller;
        setOptions(messageOption('log.search.loadingEllipsis'));
        setDropdownOpen(true);

        try {
          const response = await getFieldValues(
            {
              filed: fieldName,
              ...getTimeRangeParams(timeRange),
              limit: FIELD_VALUE_LIMIT,
              log_groups: logGroups
            },
            { signal: controller.signal }
          );
          if (
            controller.signal.aborted ||
            requestVersion !== requestVersionRef.current
          ) {
            return;
          }

          const values: FieldValueItem[] = response?.values || [];
          cacheRef.current = { scopeKey, fieldName, values };
          const currentContext = parseQueryContext(
            valueRef.current,
            realCursorPosRef.current
          );
          showValueOptions(
            values,
            currentContext.type === 'value' &&
              currentContext.fieldName === fieldName
              ? currentContext.prefix
              : ''
          );
        } catch {
          if (
            !controller.signal.aborted &&
            requestVersion === requestVersionRef.current
          ) {
            setOptions(messageOption('log.search.suggestionLoadFailed'));
            setDropdownOpen(true);
          }
        }
      },
      [
        availableFields,
        closeDropdown,
        getFieldValues,
        logGroups,
        messageOption,
        normalizedGroups.length,
        scopeKey,
        showValueOptions,
        timeRange
      ]
    );

    const scheduleFieldValues = useCallback(
      (fieldName: string) => {
        if (debounceTimerRef.current) {
          clearTimeout(debounceTimerRef.current);
        }
        debounceTimerRef.current = setTimeout(() => {
          debounceTimerRef.current = null;
          void loadFieldValues(fieldName);
        }, FIELD_VALUE_DEBOUNCE_MS);
      },
      [loadFieldValues]
    );

    const showFieldOptions = useCallback(
      (prefix: string) => {
        if (!normalizedGroups.length) {
          setOptions(messageOption('log.search.selectGroupForSuggestions'));
          setDropdownOpen(true);
          return;
        }
        if (fieldsLoading) {
          setOptions(messageOption('log.search.loadingEllipsis'));
          setDropdownOpen(true);
          return;
        }

        const normalizedPrefix = prefix.toLowerCase();
        const fields = availableFields.filter(
          (field) =>
            !HIDDEN_QUERY_FIELDS.has(field) &&
            field.toLowerCase().includes(normalizedPrefix)
        );
        if (!fields.length) {
          setOptions(messageOption('log.search.noMatchingFields'));
          setDropdownOpen(true);
          return;
        }

        setOptions(
          fields.map((field) => ({
            value: field,
            type: 'field',
            title: field,
            label: (
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">
                  {field}
                </span>
                <span className="shrink-0 text-xs text-[var(--color-text-3)]">
                  {t('log.search.field')}
                </span>
              </div>
            )
          }))
        );
        setDropdownOpen(true);
      },
      [
        availableFields,
        fieldsLoading,
        messageOption,
        normalizedGroups.length,
        t
      ]
    );

    const refreshSuggestions = useCallback(
      (inputValue: string, cursorPosition?: number | null) => {
        const context = parseQueryContext(inputValue, cursorPosition);
        if (context.type === 'field') {
          showFieldOptions(context.prefix);
          return;
        }
        if (!availableFields.includes(context.fieldName)) {
          closeDropdown();
          return;
        }

        const cached = cacheRef.current;
        if (
          cached?.scopeKey === scopeKey &&
          cached.fieldName === context.fieldName
        ) {
          showValueOptions(cached.values, context.prefix);
          return;
        }
        scheduleFieldValues(context.fieldName);
      },
      [
        availableFields,
        closeDropdown,
        scheduleFieldValues,
        scopeKey,
        showFieldOptions,
        showValueOptions
      ]
    );

    useEffect(() => {
      refreshSuggestionsRef.current = refreshSuggestions;
    }, [refreshSuggestions]);

    useEffect(() => {
      if (
        !fieldsLoading &&
        inputRef.current?.input === document.activeElement
      ) {
        refreshSuggestionsRef.current(
          valueRef.current,
          realCursorPosRef.current
        );
      }
    }, [availableFields, fieldsLoading]);

    const handleChange = useCallback(
      (nextValue: string, option?: QueryOption | QueryOption[]) => {
        const selected = Array.isArray(option) ? option[0] : option;
        const currentValue = valueRef.current;
        const isTypedChar =
          nextValue.length === currentValue.length + 1 &&
          nextValue.startsWith(currentValue);
        const isDeletedChar =
          nextValue.length === currentValue.length - 1 &&
          currentValue.startsWith(nextValue);
        // 点击候选会把输入框整段替换成 option.value，必须交给 handleSelect。
        // 输入刚好等于字段名时（例如 message 的最后一个 e）AntD 也会带上 option。
        if (
          selected?.type &&
          nextValue === selected.value &&
          !isTypedChar &&
          !isDeletedChar
        ) {
          return;
        }
        commitValue(nextValue);
        const cursorPosition =
          inputRef.current?.input?.selectionStart ?? nextValue.length;
        realCursorPosRef.current = cursorPosition;
        if (/\s$/.test(nextValue)) {
          closeDropdown();
          return;
        }
        refreshSuggestions(nextValue, cursorPosition);
      },
      [closeDropdown, commitValue, refreshSuggestions]
    );

    const restoreCursor = useCallback((cursorPosition: number) => {
      realCursorPosRef.current = cursorPosition;
      requestAnimationFrame(() => {
        const input = inputRef.current?.input;
        input?.focus();
        input?.setSelectionRange(cursorPosition, cursorPosition);
        realCursorPosRef.current = cursorPosition;
      });
    }, []);

    const applySelection = useCallback(
      (selectedValue: string, option: QueryOption) => {
        const currentValue = valueRef.current;
        const context = parseQueryContext(
          currentValue,
          realCursorPosRef.current
        );
        if (option.type === 'field') {
          const encodedField = quoteLogsqlField(selectedValue);
          const afterSelection = currentValue.slice(context.endPos);
          const suffix = afterSelection.startsWith(':') ? '' : ':';
          const nextValue = `${currentValue.slice(
            0,
            context.startPos
          )}${encodedField}${suffix}${afterSelection}`;
          const cursorPosition =
            context.startPos + encodedField.length + suffix.length;
          commitValue(nextValue);
          restoreCursor(cursorPosition);
          cacheRef.current = null;
          scheduleFieldValues(selectedValue);
          return;
        }
        if (option.type === 'value' && context.type === 'value') {
          const quotedValue = quoteLogsqlValue(selectedValue);
          const nextValue = `${currentValue.slice(
            0,
            context.startPos
          )}${quotedValue}${currentValue.slice(context.endPos)}`;
          commitValue(nextValue);
          restoreCursor(context.startPos + quotedValue.length);
          closeDropdown();
        }
      },
      [
        closeDropdown,
        commitValue,
        restoreCursor,
        scheduleFieldValues
      ]
    );

    const handleSelect = useCallback(
      (selectedValue: string, option: QueryOption) => {
        applySelection(selectedValue, option);
      },
      [applySelection]
    );

    const getHighlightedOption = useCallback((selectableOptions: QueryOption[]) => {
      const activeOption = document.querySelector(
        '.ant-select-item-option-active:not(.ant-select-item-option-disabled)'
      );
      if (!activeOption) {
        return selectableOptions[0];
      }
      const title = activeOption.getAttribute('title');
      const byTitle = selectableOptions.find(
        (option) => String(option.value) === title
      );
      if (byTitle) return byTitle;
      const labelText = activeOption
        .querySelector('.ant-select-item-option-content span')
        ?.textContent?.trim();
      return (
        selectableOptions.find((option) => String(option.value) === labelText) ||
        selectableOptions[0]
      );
    }, []);

    const handleKeyDown = useCallback(
      (event: React.KeyboardEvent<HTMLInputElement>) => {
        const selectableOptions = options.filter((option) => !option.disabled);
        const canApplySuggestion =
          dropdownOpen && selectableOptions.length > 0;

        if (event.key === 'Tab' && canApplySuggestion) {
          event.preventDefault();
          event.stopPropagation();
          const selectedOption = getHighlightedOption(selectableOptions);
          applySelection(String(selectedOption.value), selectedOption);
          return;
        }

        if (event.key !== 'Enter') return;

        if (onPressEnter) {
          event.preventDefault();
          event.stopPropagation();
          closeDropdown();
          onPressEnter();
          return;
        }

        if (canApplySuggestion) {
          event.preventDefault();
          event.stopPropagation();
          const selectedOption = getHighlightedOption(selectableOptions);
          applySelection(String(selectedOption.value), selectedOption);
        }
      },
      [
        applySelection,
        closeDropdown,
        dropdownOpen,
        getHighlightedOption,
        onPressEnter,
        options
      ]
    );

    const input = useMemo(
      () => (
        <Input
          {...inputProps}
          {...(addonAfter === undefined ? {} : { addonAfter })}
          ref={inputRef}
          placeholder={resolvedPlaceholder}
          disabled={disabled}
          allowClear={allowClear}
          onKeyDown={handleKeyDown}
          onFocus={(event) => {
            inputProps.onFocus?.(event);
            realCursorPosRef.current = event.currentTarget.selectionStart || 0;
            refreshSuggestions(
              valueRef.current,
              realCursorPosRef.current
            );
          }}
          onInput={(event) => {
            inputProps.onInput?.(event);
            realCursorPosRef.current = event.currentTarget.selectionStart || 0;
          }}
          onSelect={(event) => {
            inputProps.onSelect?.(event);
            realCursorPosRef.current = event.currentTarget.selectionStart || 0;
          }}
          onClick={(event) => {
            inputProps.onClick?.(event);
            realCursorPosRef.current = event.currentTarget.selectionStart || 0;
          }}
        />
      ),
      [
        addonAfter,
        allowClear,
        disabled,
        handleKeyDown,
        inputProps,
        refreshSuggestions,
        resolvedPlaceholder
      ]
    );

    return (
      <AutoComplete
        className={className}
        style={style}
        value={resolvedValue}
        options={options}
        disabled={disabled}
        onChange={handleChange}
        onSelect={handleSelect}
        open={dropdownOpen && options.length > 0}
        onOpenChange={setDropdownOpen}
        defaultActiveFirstOption
        filterOption={false}
        popupMatchSelectWidth
      >
        {input}
      </AutoComplete>
    );
  }
);

LogQueryInput.displayName = 'LogQueryInput';

export default LogQueryInput;
