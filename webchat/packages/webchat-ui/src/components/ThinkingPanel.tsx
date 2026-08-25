import React, { useEffect, useRef, useState } from 'react';
import { WC } from '../chrome';

function formatThinkingDuration(ms: number): string {
  const seconds = Math.max(1, Math.round(ms / 1000));
  return `思考了 ${seconds} 秒`;
}

function Chevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`h-3 w-3 transition-transform duration-200 ease-out ${expanded ? 'rotate-180' : ''}`}
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden
    >
      <path
        d="M3 4.5L6 7.5L9 4.5"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export const ThinkingPanel: React.FC<{ thinking?: string; isThinking?: boolean }> = ({
  thinking,
  isThinking,
}) => {
  const text = (thinking || '').replace(/<\/?think>/gi, '').trim();
  const [expanded, setExpanded] = useState(Boolean(isThinking));
  const [elapsedMs, setElapsedMs] = useState(0);
  const userPinnedRef = useRef(false);
  const startedAtRef = useRef<number | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isThinking) {
      if (startedAtRef.current == null) {
        startedAtRef.current = Date.now();
      }
      if (!userPinnedRef.current) {
        setExpanded(true);
      }
      return;
    }
    if (startedAtRef.current != null) {
      setElapsedMs(Date.now() - startedAtRef.current);
    }
    if (!userPinnedRef.current) {
      setExpanded(false);
    }
  }, [isThinking]);

  useEffect(() => {
    if (!isThinking) {
      return;
    }
    const tick = () => {
      setElapsedMs(Date.now() - (startedAtRef.current ?? Date.now()));
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [isThinking]);

  useEffect(() => {
    if (!isThinking || !expanded || !bodyRef.current) {
      return;
    }
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [text, isThinking, expanded]);

  if (!text && !isThinking) {
    return null;
  }

  const label = isThinking
    ? '思考中'
    : elapsedMs > 0
      ? formatThinkingDuration(elapsedMs)
      : '已完成思考';

  const toggle = () => {
    userPinnedRef.current = true;
    setExpanded((open) => !open);
  };

  return (
    <div className="min-w-0" aria-busy={Boolean(isThinking)}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={expanded}
        className="inline-flex cursor-pointer items-center gap-1.5 border-none bg-transparent p-0 text-left"
        style={{ color: WC.muted }}
      >
        <span
          className={`text-xs font-medium ${isThinking ? 'webchat-thinking-shimmer' : ''}`}
          style={isThinking ? undefined : { color: WC.muted }}
        >
          {label}
        </span>
        {isThinking ? (
          <span className="webchat-thinking-dots" aria-hidden>
            <span />
            <span />
            <span />
          </span>
        ) : null}
        <span className="flex items-center" style={{ color: WC.dim }}>
          <Chevron expanded={expanded} />
        </span>
      </button>
      <div className={`webchat-fold ${expanded ? 'is-open' : ''}`} aria-hidden={!expanded}>
        <div className="webchat-fold-inner">
          <div
            ref={bodyRef}
            className={`webchat-thinking-scroll mt-1.5 ${isThinking ? 'is-live' : ''}`}
            style={{
              borderLeft: `1.5px solid ${WC.thinkLine}`,
              color: WC.inkSoft,
            }}
          >
            <p className="m-0 whitespace-pre-wrap break-words text-xs italic leading-[1.75]">
              {text || '正在整理思路'}
              {isThinking ? <span className="webchat-thinking-caret" aria-hidden /> : null}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
