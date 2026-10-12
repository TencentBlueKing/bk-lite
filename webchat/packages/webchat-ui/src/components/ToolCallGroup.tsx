'use client';

import React, { useState } from 'react';
import type { ToolCall } from '../contentChunks';
import { useTranslator } from '../useTranslator';

export type { ToolCall };

const SUMMARY_FIELDS = ['reason', 'goal', 'thought', 'purpose', 'objective', 'description', 'summary', 'intent', 'action', 'query', 'question', 'prompt', 'message', 'filename', 'title'];

function extractSummary(args?: string): string {
  if (!args || args === '{}' || args === 'null') return '';
  try {
    const parsed = JSON.parse(args) as Record<string, unknown>;
    for (const field of SUMMARY_FIELDS) {
      const value = parsed[field];
      if (typeof value === 'string' && value.trim()) {
        const trimmed = value.trim();
        return trimmed.length > 80 ? `${trimmed.slice(0, 80)}...` : trimmed;
      }
    }
  } catch {
    return '';
  }
  return '';
}

const ToolItem: React.FC<{ tool: ToolCall }> = ({ tool }) => {
  const t = useTranslator();
  const [expanded, setExpanded] = useState(false);
  const summary = extractSummary(tool.args);
  const hasDetail = Boolean((tool.args && tool.args !== '{}') || tool.result);
  const running = tool.status === 'running';

  return (
    <div className="pl-5">
      <button
        type="button"
        className="flex w-full items-center gap-1.5 border-0 bg-transparent py-1 text-left"
        onClick={() => hasDetail && setExpanded((value) => !value)}
      >
        <span className="text-xs text-[var(--color-success)]">{running ? '…' : '✓'}</span>
        <span className="text-[8px] text-[var(--color-text-4)]">{expanded ? '▾' : '▸'}</span>
        <span className="min-w-0 flex-1 text-xs">
          <span className="font-medium text-[var(--color-text-1)]">{tool.name}</span>
          {summary ? <span className="ml-2 text-[var(--color-text-3)]">· {summary}</span> : null}
        </span>
      </button>
      {expanded && hasDetail ? (
        <div className="pl-8 text-xs">
          {tool.args && tool.args !== '{}' ? (
            <div className="mb-2">
              <div className="mb-1 font-medium text-[var(--color-text-2)]">{t('chat.toolCall.params', '参数')}</div>
              <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-words rounded bg-[var(--color-fill-2)] p-2 text-[11px]">{tool.args}</pre>
            </div>
          ) : null}
          {tool.result ? (
            <div>
              <div className="mb-1 font-medium text-[var(--color-text-2)]">{t('chat.toolCall.result', '结果')}</div>
              <pre className="m-0 max-h-[300px] overflow-auto whitespace-pre-wrap break-words rounded bg-[var(--color-fill-2)] p-2 text-[11px]">{tool.result}</pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

export const ToolCallGroup: React.FC<{ toolCalls: ToolCall[] }> = ({ toolCalls }) => {
  const t = useTranslator();
  const [expanded, setExpanded] = useState(false);
  if (toolCalls.length === 0) return null;
  const running = toolCalls.some((tool) => tool.status === 'running');
  return (
    <div className="my-1">
      <button
        type="button"
        className="inline-flex cursor-pointer items-center gap-1.5 rounded border-0 bg-transparent px-2 py-1 text-xs text-[var(--color-text-3)]"
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="text-[8px] text-[var(--color-text-4)]">{expanded || running ? '▾' : '▸'}</span>
        <span className="text-xs text-[var(--color-success)]">{running ? '…' : '✓'}</span>
        <span>{t('chat.toolCall.calledCount', '已调用 {count} 个工具', { count: toolCalls.length })}</span>
        {!running ? (
          <span className="text-[var(--color-text-4)]">
            {expanded ? t('chat.toolCall.collapseHint', '点击收起') : t('chat.toolCall.expandHint', '点击展开查看详情')}
          </span>
        ) : null}
      </button>
      {expanded || running ? (
        <div className="mt-1">
          {toolCalls.map((tool) => <ToolItem key={tool.id} tool={tool} />)}
        </div>
      ) : null}
    </div>
  );
};
