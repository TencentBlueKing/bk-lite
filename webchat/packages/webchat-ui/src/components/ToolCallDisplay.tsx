import React, { useState } from 'react';

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
    <div className="flex flex-row flex-wrap items-center gap-2">
      {toolCalls.map((tool) => (
        <ToolCallTag key={tool.id} tool={tool} />
      ))}
    </div>
  );
};

interface ToolCallTagProps {
  tool: ToolCall;
}

const ToolCallTag: React.FC<ToolCallTagProps> = ({ tool }) => {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div 
      className="relative inline-flex"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div className="inline-flex items-center gap-1.5 bg-green-50 text-green-700 px-3 py-1 rounded-full text-xs font-medium border border-green-200">
        <span className="inline-flex items-center gap-1">
          <span>🛠️</span>
          <span>{tool.name}</span>
        </span>
        {tool.status === 'running' ? (
          <svg 
            className="animate-spin h-3 w-3 text-green-600" 
            xmlns="http://www.w3.org/2000/svg" 
            fill="none" 
            viewBox="0 0 24 24"
          >
            <circle 
              className="opacity-25" 
              cx="12" 
              cy="12" 
              r="10" 
              stroke="currentColor" 
              strokeWidth="4"
            />
            <path 
              className="opacity-75" 
              fill="currentColor" 
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        ) : (
          <svg 
            className="h-3 w-3 text-green-600" 
            xmlns="http://www.w3.org/2000/svg" 
            viewBox="0 0 20 20" 
            fill="currentColor"
          >
            <path 
              fillRule="evenodd" 
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" 
              clipRule="evenodd" 
            />
          </svg>
        )}
      </div>
      
      {/* Tooltip */}
      {showTooltip && tool.result && (
        <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 z-50 w-max max-w-xs">
          <div className="bg-gray-900 text-white text-xs rounded-lg px-3 py-2 shadow-lg">
            <div className="font-semibold mb-1">执行结果:</div>
            <div className="text-gray-200 max-h-40 overflow-y-auto whitespace-pre-wrap break-words">
              {formatResult(tool.result)}
            </div>
          </div>
          {/* Arrow */}
          <div className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-gray-900" />
        </div>
      )}
    </div>
  );
};

function formatResult(result: string): string {
  if (result.length > 300) {
    return result.substring(0, 300) + '...';
  }
  
  try {
    const parsed = JSON.parse(result);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return result;
  }
}
