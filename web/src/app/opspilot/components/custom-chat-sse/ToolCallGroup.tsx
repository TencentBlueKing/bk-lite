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
    <div style={{ paddingLeft: 20 }}>
      <div
        onClick={() => hasDetail && setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 0',
          cursor: hasDetail ? 'pointer' : 'default',
          borderRadius: 4,
        }}
        className="tool-item-header"
      >
        <span style={{ flexShrink: 0, width: 16, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
          {isCalling ? (
            <span style={{
              display: 'inline-block', width: 10, height: 10,
              border: '1.5px solid #1677ff', borderTopColor: 'transparent',
              borderRadius: '50%', animation: 'tool-spin 0.8s linear infinite'
            }} />
          ) : (
            <span style={{ color: '#52c41a', fontSize: 12 }}>✓</span>
          )}
        </span>
        {hasDetail && (
          <span style={{
            fontSize: 8, width: 12, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--color-text-4)', transition: 'transform 0.2s',
            transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)'
          }}>▶</span>
        )}
        {!hasDetail && <span style={{ width: 12 }} />}
        <span style={{ flex: 1, minWidth: 0, fontSize: 12, lineHeight: 1.5 }}>
          <span style={{ color: 'var(--color-text-1)', fontWeight: 500 }}>{tool.name}</span>
          {summary && (
            <span style={{ marginLeft: 8, color: 'var(--color-text-3)' }}>· {summary}</span>
          )}
          {choiceResult && (
            <span style={{
              marginLeft: 8, padding: '1px 8px',
              background: 'var(--color-primary-light-1, #e6f4ff)',
              color: 'var(--color-primary-6, #1677ff)',
              borderRadius: 10, fontSize: 11, fontWeight: 500
            }}>→ {choiceResult}</span>
          )}
        </span>
      </div>
      {expanded && hasDetail && (
        <div style={{ paddingLeft: 34, fontSize: 12 }}>
          {argsFormatted && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontWeight: 500, color: 'var(--color-text-2)', marginBottom: 4 }}>参数:</div>
              <pre style={{
                margin: 0, padding: 8, background: 'var(--color-fill-2)',
                borderRadius: 4, fontSize: 11, overflowX: 'auto',
                whiteSpace: 'pre-wrap', wordBreak: 'break-word'
              }}>{argsFormatted}</pre>
            </div>
          )}
          {tool.result && (
            <div>
              <div style={{ fontWeight: 500, color: 'var(--color-text-2)', marginBottom: 4 }}>结果:</div>
              <pre style={{
                margin: 0, padding: 8, background: 'var(--color-fill-2)',
                borderRadius: 4, fontSize: 11, overflowX: 'auto',
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                maxHeight: 300, overflowY: 'auto'
              }}>{tool.result}</pre>
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
    <div style={{ margin: '4px 0' }}>
      <div
        onClick={() => !shouldAutoExpand && setExpanded(!expanded)}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '4px 8px', cursor: 'pointer', userSelect: 'none',
          fontSize: 12, color: 'var(--color-text-3)', borderRadius: 4, margin: '2px 0'
        }}
        className="tool-group-header"
      >
        <span style={{
          fontSize: 8, width: 12, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          transition: 'transform 0.2s', transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)'
        }}>▶</span>
        <span style={{ display: 'inline-flex', alignItems: 'center' }}>
          {hasRunning ? (
            <span style={{
              display: 'inline-block', width: 10, height: 10,
              border: '1.5px solid #1677ff', borderTopColor: 'transparent',
              borderRadius: '50%', animation: 'tool-spin 0.8s linear infinite'
            }} />
          ) : (
            <span style={{ color: '#52c41a', fontSize: 12 }}>✓</span>
          )}
        </span>
        <span>已调用 {totalCount} 个工具</span>
        {!shouldAutoExpand && (
          <span style={{ color: 'var(--color-text-4)' }}>
            {expanded ? '点击收起' : '点击展开查看详情'}
          </span>
        )}
        {shouldAutoExpand && (
          <span style={{ color: 'var(--color-text-4)' }}>执行中...</span>
        )}
      </div>
      {isExpanded && (
        <div style={{ marginTop: 4 }}>
          {toolCalls.map(tool => (
            <ToolItem key={tool.id} tool={tool} />
          ))}
        </div>
      )}
    </div>
  );
};

export default ToolCallGroup;
