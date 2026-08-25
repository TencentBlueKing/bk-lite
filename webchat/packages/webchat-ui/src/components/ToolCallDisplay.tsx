import React, { useState } from 'react';
import type { ToolCall } from '../contentChunks';
import { WC } from '../chrome';

export type { ToolCall };

interface ToolCallDisplayProps {
  toolCalls: ToolCall[];
}

export const ToolCallDisplay: React.FC<ToolCallDisplayProps> = ({ toolCalls }) => {
  if (toolCalls.length === 0) return null;

  return (
    <div className="flex flex-col gap-0.5">
      {toolCalls.map((tool) => (
        <ToolCallRow key={tool.id} tool={tool} />
      ))}
    </div>
  );
};

const Spinner: React.FC = () => (
  <svg
    className="h-3 w-3 motion-safe:animate-spin"
    style={{ color: WC.indigo }}
    xmlns="http://www.w3.org/2000/svg"
    fill="none"
    viewBox="0 0 24 24"
    aria-hidden
  >
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    />
  </svg>
);

const Check: React.FC = () => (
  <svg
    className="h-3 w-3"
    style={{ color: WC.indigo }}
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 20 20"
    fill="currentColor"
    aria-hidden
  >
    <path
      fillRule="evenodd"
      d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
      clipRule="evenodd"
    />
  </svg>
);

const Chevron: React.FC<{ expanded: boolean }> = ({ expanded }) => (
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

const ToolCallRow: React.FC<{ tool: ToolCall }> = ({ tool }) => {
  const [expanded, setExpanded] = useState(false);
  const running = tool.status === 'running';
  const result = tool.result?.trim();
  const canExpand = Boolean(result);

  return (
    <div className="webchat-tool-row min-w-0">
      <button
        type="button"
        disabled={!canExpand}
        aria-expanded={canExpand ? expanded : undefined}
        onClick={() => {
          if (canExpand) {
            setExpanded((open) => !open);
          }
        }}
        className="inline-flex max-w-full items-center gap-1.5 border-none bg-transparent p-0 text-left"
        style={{ color: WC.muted, cursor: canExpand ? 'pointer' : 'default' }}
      >
        {running ? <Spinner /> : <Check />}
        <span className="text-xs">{running ? '正在使用' : '已使用'}</span>
        <span
          className="min-w-0 truncate font-mono text-[11px] leading-4"
          style={{ color: running ? WC.botText : WC.inkSoft }}
        >
          {tool.name}
        </span>
        {canExpand ? (
          <span className="flex items-center" style={{ color: WC.dim }}>
            <Chevron expanded={expanded} />
          </span>
        ) : null}
      </button>
      {canExpand ? (
        <div className={`webchat-fold ${expanded ? 'is-open' : ''}`}>
          <div className="webchat-fold-inner">
            <pre
              className="mb-0 mt-1 max-h-36 overflow-y-auto whitespace-pre-wrap break-words rounded-md px-2 py-1.5 font-mono text-[11px] leading-[1.55]"
              style={{ background: WC.page, color: WC.inkSoft }}
            >
              {formatResult(result as string)}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
};

function formatResult(result: string): string {
  if (result.length > 300) {
    return `${result.slice(0, 300)}…`;
  }

  try {
    const parsed = JSON.parse(result);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return result;
  }
}
