'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { stableStringify } from '@/app/ops-analysis/utils/optionsQueryParamRefs';
import {
  OPTIONS_QUERY_TEXT_DEBOUNCE_MS,
  isOptionsQueryTextEmpty,
} from '@/app/ops-analysis/utils/optionsQueryTextDebounce';

const pick = (
  values: Record<string, unknown>,
  keys: ReadonlySet<string>,
): Record<string, unknown> => {
  const picked: Record<string, unknown> = {};
  keys.forEach((key) => {
    if (Object.prototype.hasOwnProperty.call(values, key)) {
      picked[key] = values[key];
    }
  });
  return picked;
};

const clearTimer = (timers: Map<string, number>, key: string) => {
  const timer = timers.get(key);
  if (timer === undefined) return;
  window.clearTimeout(timer);
  timers.delete(key);
};

/**
 * 只推迟会写进选项查询签名的文本/数字。
 * 键第一次出现时立刻采用（打开表单、灌入已有值）；之后的非空修改尾随防抖。
 * 变成空值立刻采用，方便下游马上 blocked 并丢掉在途结果。
 * 不在 textKeys 里的键（下拉、单选等）始终用当前值。
 */
export const useDebouncedOptionsQueryValues = <T extends Record<string, unknown>>(
  values: T,
  textKeys: readonly string[],
  delay = OPTIONS_QUERY_TEXT_DEBOUNCE_MS,
): T => {
  const textKeySignature = textKeys.join('\0');
  const textKeySet = useMemo(() => new Set(textKeys), [textKeySignature]);
  const liveSignature = stableStringify(pick(values, textKeySet));
  const valuesRef = useRef(values);
  const textKeysRef = useRef(textKeys);
  valuesRef.current = values;
  textKeysRef.current = textKeys;

  const [debouncedText, setDebouncedText] = useState<Record<string, unknown>>(() => (
    pick(values, new Set(textKeys))
  ));
  const debouncedRef = useRef(debouncedText);
  debouncedRef.current = debouncedText;
  const timersRef = useRef(new Map<string, number>());

  useEffect(() => {
    const timers = timersRef.current;
    const keys = new Set(textKeysRef.current);
    const liveText = pick(valuesRef.current, keys);
    const current = debouncedRef.current;
    const immediate: Record<string, unknown> = { ...current };
    let immediateChanged = false;

    Object.keys(current).forEach((key) => {
      if (keys.has(key) && Object.prototype.hasOwnProperty.call(liveText, key)) return;
      delete immediate[key];
      immediateChanged = true;
      clearTimer(timers, key);
    });

    keys.forEach((key) => {
      if (!Object.prototype.hasOwnProperty.call(liveText, key)) return;
      const next = liveText[key];
      const seen = Object.prototype.hasOwnProperty.call(current, key);
      if (!seen || isOptionsQueryTextEmpty(next)) {
        if (!seen || !Object.is(current[key], next)) {
          immediate[key] = next;
          immediateChanged = true;
        }
        clearTimer(timers, key);
        return;
      }
      if (Object.is(current[key], next)) {
        clearTimer(timers, key);
        return;
      }
      clearTimer(timers, key);
      const timer = window.setTimeout(() => {
        timers.delete(key);
        setDebouncedText((prev) => {
          if (Object.is(prev[key], next)) return prev;
          return { ...prev, [key]: next };
        });
      }, delay);
      timers.set(key, timer);
    });

    if (immediateChanged) setDebouncedText(immediate);
  }, [delay, liveSignature, textKeySignature]);

  useEffect(() => () => {
    timersRef.current.forEach((timer) => window.clearTimeout(timer));
    timersRef.current.clear();
  }, []);

  return useMemo(() => {
    let changed = false;
    const merged: Record<string, unknown> = { ...values };
    textKeySet.forEach((key) => {
      if (!Object.prototype.hasOwnProperty.call(debouncedText, key)) return;
      if (Object.is(merged[key], debouncedText[key])) return;
      merged[key] = debouncedText[key];
      changed = true;
    });
    return changed ? merged as T : values;
  }, [debouncedText, textKeySet, values]);
};
