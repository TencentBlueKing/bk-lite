import React from 'react';

export interface ToolCall {
  id: string;
  name: string;
  args?: string;
  result?: string;
  status: 'running' | 'completed';
}

interface ToolCallDisplayProps {
  toolCalls: ToolCall[];
}

export const ToolCallDisplay: React.FC<ToolCallDisplayProps> = ({ toolCalls }) => {
  if (toolCalls.length === 0) return null;

  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-3 border border-blue-200 shadow-sm">
      <div className="text-xs font-semibold text-indigo-700 mb-2 flex items-center gap-1">
        🛠️ 工具调用
      </div>
      <div className="space-y-2">
        {toolCalls.map((tool) => (
          <ToolCallItem key={tool.id} tool={tool} />
        ))}
      </div>
    </div>
  );
};

interface ToolCallItemProps {
  tool: ToolCall;
}

const ToolCallItem: React.FC<ToolCallItemProps> = ({ tool }) => {
  return (
    <div className="bg-white/50 rounded-lg p-2">
      <div className="flex items-center gap-2 text-sm">
        <span 
          className={`inline-block w-2 h-2 rounded-full ${
            tool.status === 'running' 
              ? 'bg-yellow-400 animate-pulse' 
              : 'bg-green-500'
          }`}
        />
        <span className="font-medium text-gray-800">{tool.name}</span>
        <span className="text-xs text-gray-500">
          {tool.status === 'running' ? '运行中...' : '完成'}
        </span>
      </div>
      
      {tool.args && (
        <div className="mt-2">
          <div className="text-xs text-gray-500 mb-1">参数:</div>
          <div className="text-xs text-gray-700 bg-white rounded px-2 py-1 font-mono border border-gray-200">
            {formatArgs(tool.args)}
          </div>
        </div>
      )}
      
      {tool.result && (
        <div className="mt-2">
          <div className="text-xs text-gray-500 mb-1">结果:</div>
          <div className="text-xs text-green-700 bg-green-50 rounded px-2 py-1 border border-green-200">
            {formatResult(tool.result)}
          </div>
        </div>
      )}
    </div>
  );
};

function formatArgs(args: string): string {
  try {
    const parsed = JSON.parse(args);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return args;
  }
}

function formatResult(result: string): string {
  if (result.length > 150) {
    return result.substring(0, 150) + '...';
  }
  
  try {
    const parsed = JSON.parse(result);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return result;
  }
}
