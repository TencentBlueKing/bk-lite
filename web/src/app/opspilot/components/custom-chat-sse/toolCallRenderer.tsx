/**
 * 工具调用渲染器
 * 负责生成工具调用和错误消息的 HTML
 */

export interface ToolCallInfo {
  name: string;
  args: string;
  status: 'calling' | 'completed';
  result?: string;
}

/**
 * 渲染单个工具调用卡片
 */
export const renderToolCallCard = (id: string, info: ToolCallInfo): string => {
  const isCalling = info.status === 'calling';
  
  const statusConfig = isCalling 
    ? {
      borderColor: 'border-blue-400',
      bgClass: 'bg-gradient-to-br from-blue-50 to-blue-100/50 dark:from-blue-900/20 dark:to-blue-800/10',
      statusText: '执行中',
      statusClass: 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/30',
      iconClass: 'animate-pulse'
    }
    : {
      borderColor: 'border-green-400',
      bgClass: 'bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-800/10',
      statusText: '已完成',
      statusClass: 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/30',
      iconClass: ''
    };

  const argsHtml = info.args 
    ? `<div class="mt-3">
         <div class="text-xs font-semibold text-[var(--color-text-2)] mb-1.5">参数</div>
         <code class="text-sm text-[var(--color-text-1)] break-all font-medium">${info.args}</code>
       </div>`
    : '';

  const resultHtml = info.result 
    ? `<div class="mt-3">
         <div class="text-xs font-semibold text-[var(--color-text-2)] mb-1.5">结果</div>
         <pre class="text-sm text-[var(--color-text-1)] whitespace-pre-wrap break-words m-0 font-medium">${info.result}</pre>
       </div>`
    : '';

  return `<div class="my-3 p-4 rounded-lg border-l-4 ${statusConfig.borderColor} ${statusConfig.bgClass}" data-tool-id="${id}">
    <div class="flex items-center gap-2">
      <span class="text-lg ${statusConfig.iconClass}">🔧</span>
      <span class="font-medium text-base text-[var(--color-text-2)]">${info.name}</span>
      <span class="ml-auto text-xs px-2 py-1 rounded ${statusConfig.statusClass} font-medium">${statusConfig.statusText}</span>
    </div>
    ${argsHtml}
    ${resultHtml}
  </div>`;
};

/**
 * 渲染所有工具调用
 */
export const renderAllToolCalls = (toolCalls: Map<string, ToolCallInfo>): string => {
  return Array.from(toolCalls.entries())
    .map(([id, info]) => renderToolCallCard(id, info))
    .join('');
};

/**
 * 渲染错误消息卡片
 */
export const renderErrorMessage = (error: string, type: 'error' | 'run_error' = 'error', errorCode?: string): string => {
  const config = type === 'run_error'
    ? {
      icon: '⚠️',
      title: `运行错误${errorCode ? ` (${errorCode})` : ''}`
    }
    : {
      icon: '❌',
      title: '执行出错'
    };

  return `<div class="my-3 p-4 rounded-lg border-l-4 border-red-500 bg-gradient-to-br from-[var(--color-fill-2)] to-red-50/5 shadow-md">
    <div class="flex items-center gap-2 mb-2">
      <span class="text-lg">${config.icon}</span>
      <span class="flex-1 font-semibold text-sm text-red-500">${config.title}</span>
    </div>
    <div class="p-2 bg-[var(--color-fill-3)] rounded text-xs text-[var(--color-text-2)] font-mono">${error}</div>
  </div>`;
};
