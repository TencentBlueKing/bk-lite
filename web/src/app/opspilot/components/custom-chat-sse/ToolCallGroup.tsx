'use client';

import React, { useState, useMemo } from 'react';

interface ToolCallData {
  id: string;
  name: string;
  args: string;
  status: 'calling' | 'completed';
  result?: string;
}

interface ToolCallGroupProps {
  toolCalls: ToolCallData[];
  isStreaming?: boolean;
}

const extractSummary = (args: string, toolName?: string): string => {
  if (!args || args === '{}' || args === '""' || args === 'null') {
    return toolName || '';
  }
  try {
    const parsed = JSON.parse(args);
    if (typeof parsed === 'object' && parsed !== null && Object.keys(parsed).length === 0) {
      return '';
    }
    const summaryFields = [
      'reason', 'goal', 'thought', 'purpose', 'objective',
      'description', 'summary', 'intent', 'action',
      'query', 'question', 'prompt', 'message', 'content', 'text',
      'command', 'instruction', 'task', 'input'
    ];
    for (const field of summaryFields) {
      const value = parsed[field];
      if (typeof value === 'string' && value.trim()) {
        const trimmed = value.trim();
        return trimmed.length > 80 ? trimmed.slice(0, 80) + '...' : trimmed;
      }
    }
    for (const [key, value] of Object.entries(parsed)) {
      if (['id', 'name', 'type', 'format', 'encoding', 'tool', 'tool_name'].includes(key)) continue;
      if (typeof value === 'string' && value.trim() && value.length >= 3 && value.length < 200) {
        const trimmed = value.trim();
        return trimmed.length > 80 ? trimmed.slice(0, 80) + '...' : trimmed;
      }
    }
    return '';
  } catch {
    return '';
  }
};

const extractChoiceResult = (result?: string): string => {
  if (!result) return '';
  const match = result.match(/(?:用户回答|选择了|默认选项)[:：]\s*(.+?)(?:[。.]|(?:\s*\(keys:)|$)/);
  return match ? match[1].trim() : '';
};

const formatJson = (str: string): string => {
  if (!str || str === '{}' || str === '""' || str === 'null') return '';
  try {
    const parsed = JSON.parse(str);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return str;
  }
};

const ToolSpinner = () => (
  <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border-[1.5px] border-[var(--color-primary)] border-t-transparent" />
);

const ToolItem: React.FC<{ tool: ToolCallData }> = ({ tool }) => {
  const [expanded, setExpanded] = useState(false);
  const summary = useMemo(() => extractSummary(tool.args, tool.name), [tool.args, tool.name]);
  const choiceResult = useMemo(
    () => tool.name === 'request_user_choice' ? extractChoiceResult(tool.result) : '',
    [tool.name, tool.result]
  );

  const hasDetail = !!(tool.args && tool.args !== '{}') || !!tool.result;
  const argsFormatted = formatJson(tool.args);
  const isCalling = tool.status === 'calling';

  return (
    <div className="pl-5">
      <div
        onClick={() => hasDetail && setExpanded(!expanded)}
        className={[
          'tool-item-header flex items-center gap-1.5 rounded py-1',
          hasDetail ? 'cursor-pointer' : 'cursor-default',
        ].join(' ')}
      >
        <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center">
          {isCalling ? (
            <ToolSpinner />
          ) : (
            <span className="text-xs text-[var(--color-success)]">✓</span>
          )}
        </span>
        {hasDetail && (
          <span className={[
            'inline-flex h-3 w-3 items-center justify-center text-[8px] text-[var(--color-text-4)] transition-transform duration-200',
            expanded ? 'rotate-90' : 'rotate-0',
          ].join(' ')}>▶</span>
        )}
        {!hasDetail && <span className="w-3" />}
        <span className="min-w-0 flex-1 text-xs leading-normal">
          <span className="font-medium text-[var(--color-text-1)]">{tool.name}</span>
          {summary && (
            <span className="ml-2 text-[var(--color-text-3)]">· {summary}</span>
          )}
          {choiceResult && (
            <span className="ml-2 rounded-[10px] bg-[var(--color-primary-light-1)] px-2 py-px text-[11px] font-medium text-[var(--color-primary)]">→ {choiceResult}</span>
          )}
        </span>
      </div>
      {expanded && hasDetail && (
        <div className="pl-[34px] text-xs">
          {argsFormatted && (
            <div className="mb-2">
              <div className="mb-1 font-medium text-[var(--color-text-2)]">参数:</div>
              <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-words rounded bg-[var(--color-fill-2)] p-2 text-[11px]">{argsFormatted}</pre>
            </div>
          )}
          {tool.result && (
            <div>
              <div className="mb-1 font-medium text-[var(--color-text-2)]">结果:</div>
              <pre className="m-0 max-h-[300px] overflow-x-auto overflow-y-auto whitespace-pre-wrap break-words rounded bg-[var(--color-fill-2)] p-2 text-[11px]">{tool.result}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const ToolCallGroup: React.FC<ToolCallGroupProps> = ({ toolCalls, isStreaming }) => {
  const [expanded, setExpanded] = useState(false);
  const completedCount = toolCalls.filter(t => t.status === 'completed').length;
  const totalCount = toolCalls.length;
  const hasRunning = completedCount < totalCount;
  const shouldAutoExpand = isStreaming || hasRunning;

  const isExpanded = shouldAutoExpand || expanded;

  return (
    <div className="my-1">
      <div
        onClick={() => !shouldAutoExpand && setExpanded(!expanded)}
        className="tool-group-header my-0.5 inline-flex cursor-pointer select-none items-center gap-1.5 rounded px-2 py-1 text-xs text-[var(--color-text-3)]"
      >
        <span className={[
          'inline-flex h-3 w-3 items-center justify-center text-[8px] transition-transform duration-200',
          isExpanded ? 'rotate-90' : 'rotate-0',
        ].join(' ')}>▶</span>
        <span className="inline-flex items-center">
          {hasRunning ? (
            <ToolSpinner />
          ) : (
            <span className="text-xs text-[var(--color-success)]">✓</span>
          )}
        </span>
        <span>已调用 {totalCount} 个工具</span>
        {!shouldAutoExpand && (
          <span className="text-[var(--color-text-4)]">
            {expanded ? '点击收起' : '点击展开查看详情'}
          </span>
        )}
        {shouldAutoExpand && (
          <span className="text-[var(--color-text-4)]">执行中...</span>
        )}
      </div>
      {isExpanded && (
        <div className="mt-1">
          {toolCalls.map(tool => (
            <ToolItem key={tool.id} tool={tool} />
          ))}
        </div>
      )}
    </div>
  );
};

export default ToolCallGroup;
