import {
  type ChangeEvent,
  type CompositionEvent,
  useEffect,
  useRef,
  useState,
} from 'react';

export * from '@bk-lite/chat-content/imeKeyboard';

function isChangeEventComposing(
  event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
): boolean {
  const native = event.nativeEvent as InputEvent & { isComposing?: boolean };
  return Boolean(native.isComposing);
}

/**
 * Controlled search input that keeps draft text during IME composition, but only
 * commits the filter/query after composition ends (or for non-IME keystrokes).
 * Avoids pinyin intermediates like "guan" filtering English titles mid-input.
 */
export function useImeSafeSearchInput(
  committed: string,
  onCommit: (value: string) => void,
) {
  const [draft, setDraft] = useState(committed);
  const composingRef = useRef(false);
  const onCommitRef = useRef(onCommit);
  onCommitRef.current = onCommit;

  useEffect(() => {
    if (!composingRef.current) {
      setDraft(committed);
    }
  }, [committed]);

  const commit = (value: string) => {
    setDraft(value);
    onCommitRef.current(value);
  };

  return {
    value: draft,
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const value = event.target.value;
      setDraft(value);
      if (composingRef.current || isChangeEventComposing(event)) {
        return;
      }
      onCommitRef.current(value);
    },
    onCompositionStart: () => {
      composingRef.current = true;
    },
    onCompositionEnd: (
      event: CompositionEvent<HTMLInputElement | HTMLTextAreaElement>,
    ) => {
      composingRef.current = false;
      commit(event.currentTarget.value);
    },
    onSearch: (value: string) => {
      composingRef.current = false;
      commit(value);
    },
  };
}
