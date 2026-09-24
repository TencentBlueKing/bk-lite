import React, { useState } from 'react';
import type { ToolCall } from '../contentChunks';
import { WC } from '../chrome';

export type { ToolCall };

const SUMMARY_FIELDS = [
  'reason',
  'goal',
  'thought',
  'purpose',
  'objective',
  'description',
  'summary',
  'intent',
  'action',
  'query',
  'question',
  'prompt',
  'message',
  'content',
  'text',
  'command',
  'instruction',
  'task',
  'input',
  'inst_name',
  'model_id',
];

const SKIP_SUMMARY_KEYS = new Set(['id', 'name', 'type', 'format', 'encoding', 'tool', 'tool_name']);

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
  const argsFormatted = formatToolCallJson(tool.args, { hideEmptyObject: true });
  const resultFormatted = formatToolCallJson(tool.result);
  const canExpand = Boolean(argsFormatted || resultFormatted);
  const summary = extractToolCallSummary(tool.args);

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
        {summary ? (
          <span className="min-w-0 truncate text-[11px] leading-4" style={{ color: WC.dim }}>
            · {summary}
          </span>
        ) : null}
        {canExpand ? (
          <span className="flex items-center" style={{ color: WC.dim }}>
            <Chevron expanded={expanded} />
          </span>
        ) : null}
      </button>
      {canExpand ? (
        <div className={`webchat-fold ${expanded ? 'is-open' : ''}`}>
          <div className="webchat-fold-inner">
            {argsFormatted ? (
              <ToolCallDetailBlock label="参数" value={argsFormatted} />
            ) : null}
            {resultFormatted ? (
              <ToolCallDetailBlock label="结果" value={resultFormatted} />
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
};

const ToolCallDetailBlock: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="mt-1">
    <div className="mb-0.5 text-[11px] font-medium" style={{ color: WC.inkSoft }}>
      {`${label}:`}
    </div>
    <pre
      className="mb-0 max-h-36 overflow-y-auto whitespace-pre-wrap break-words rounded-md px-2 py-1.5 font-mono text-[11px] leading-[1.55]"
      style={{ background: WC.page, color: WC.inkSoft }}
    >
      {value}
    </pre>
  </div>
);

function clipPreview(value: string, max = 80): string {
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

export function formatToolCallJson(
  value?: string,
  options?: { hideEmptyObject?: boolean }
): string {
  if (!value || !value.trim()) {
    return '';
  }
  const trimmed = value.trim();
  if (options?.hideEmptyObject && (trimmed === '{}' || trimmed === '""' || trimmed === 'null')) {
    return '';
  }
  try {
    return JSON.stringify(JSON.parse(trimmed), null, 2);
  } catch {
    return trimmed;
  }
}

export function extractToolCallSummary(args?: string): string {
  const formatted = formatToolCallJson(args, { hideEmptyObject: true });
  if (!formatted) {
    return '';
  }
  try {
    const parsed = JSON.parse(args as string);
    if (typeof parsed !== 'object' || parsed === null) {
      return clipPreview(String(parsed));
    }
    if (Array.isArray(parsed.query_list) && parsed.query_list.length > 0) {
      return clipPreview(JSON.stringify(parsed.query_list));
    }
    for (const field of SUMMARY_FIELDS) {
      const value = (parsed as Record<string, unknown>)[field];
      if (typeof value === 'string' && value.trim()) {
        return clipPreview(value.trim());
      }
    }
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (SKIP_SUMMARY_KEYS.has(key)) continue;
      if (typeof value === 'string' && value.trim() && value.length >= 3) {
        return clipPreview(value.trim());
      }
    }
    const keys = Object.keys(parsed as Record<string, unknown>);
    if (keys.length > 0 && keys.length <= 5) {
      const preview = keys
        .map((key) => {
          const value = (parsed as Record<string, unknown>)[key];
          if (typeof value === 'string') return `${key}: ${clipPreview(value, 20)}`;
          if (typeof value === 'number' || typeof value === 'boolean') return `${key}: ${value}`;
          return `${key}: …`;
        })
        .join(', ');
      return clipPreview(preview);
    }
  } catch {
    return clipPreview(formatted.replace(/\s+/g, ' '));
  }
  return '';
}
