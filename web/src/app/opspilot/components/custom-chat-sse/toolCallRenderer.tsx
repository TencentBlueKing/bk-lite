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
 * 初始化全局 tooltip（只执行一次）
 */
let tooltipInitialized = false;
let tooltipElement: HTMLDivElement | null = null;

const initGlobalTooltip = () => {
  if (tooltipInitialized) return;
  tooltipInitialized = true;

  // 创建全局 tooltip 元素
  tooltipElement = document.createElement('div');
  tooltipElement.className = 'tool-call-tooltip';
  tooltipElement.style.cssText = `
    position: fixed;
    z-index: 99999;
    padding: 8px 12px;
    background: rgba(0, 0, 0, 0.85);
    color: white;
    font-size: 12px;
    line-height: 1.5;
    border-radius: 6px;
    max-width: 400px;
    word-wrap: break-word;
    white-space: pre-wrap;
    pointer-events: none;
    display: none;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  `;
  document.body.appendChild(tooltipElement);

  // 使用事件委托处理所有 tool-call-tag 的 hover
  document.addEventListener('mouseover', (e) => {
    const target = (e.target as HTMLElement).closest('.tool-call-tag') as HTMLElement;
    if (target && tooltipElement) {
      const result = target.getAttribute('data-result');
      if (result) {
        tooltipElement.textContent = result;
        tooltipElement.style.display = 'block';
        
        // 计算位置
        const rect = target.getBoundingClientRect();
        const tooltipRect = tooltipElement.getBoundingClientRect();
        
        let top = rect.bottom + 8;
        let left = rect.left + rect.width / 2 - tooltipRect.width / 2;
        
        // 防止超出屏幕
        if (left < 8) left = 8;
        if (left + tooltipRect.width > window.innerWidth - 8) {
          left = window.innerWidth - tooltipRect.width - 8;
        }
        if (top + tooltipRect.height > window.innerHeight - 8) {
          top = rect.top - tooltipRect.height - 8;
        }
        
        tooltipElement.style.top = `${top}px`;
        tooltipElement.style.left = `${left}px`;
      }
    }
  });

  document.addEventListener('mouseout', (e) => {
    const target = (e.target as HTMLElement).closest('.tool-call-tag');
    if (target && tooltipElement) {
      tooltipElement.style.display = 'none';
    }
  });
};

/**
 * 确保 tooltip 已初始化
 */
export const initToolCallTooltips = () => {
  if (typeof window !== 'undefined') {
    initGlobalTooltip();
  }
};

/**
 * 渲染单个工具调用 Tag
 */
export const renderToolCallCard = (id: string, info: ToolCallInfo): string => {
  const isCalling = info.status === 'calling';

  // 转义 HTML
  const escapeHtml = (text: string) => {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  // 根据状态决定颜色
  const bgColor = isCalling ? 'rgba(22, 119, 255, 0.1)' : 'rgba(82, 196, 26, 0.1)';
  const borderColor = isCalling ? '#1677ff' : '#52c41a';
  const textColor = isCalling ? '#1677ff' : '#52c41a';

  // Spin 动画样式
  const spinStyle = isCalling ? `<style>
    @keyframes tool-spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  </style>` : '';

  // 状态图标
  const statusIcon = isCalling 
    ? `<span style="display: inline-block; width: 12px; height: 12px; margin-left: 6px; border: 2px solid ${textColor}; border-top-color: transparent; border-radius: 50%; animation: tool-spin 0.8s linear infinite;"></span>`
    : `<span style="display: inline-block; margin-left: 6px; color: ${textColor};">✓</span>`;

  const cursor = info.result ? 'help' : 'default';
  const resultAttr = info.result ? `data-result="${escapeHtml(info.result)}"` : '';

  return `${spinStyle}<span class="tool-call-tag" data-tool-id="${id}" ${resultAttr} style="display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; margin-right: 8px; font-size: 13px; line-height: 20px; background: ${bgColor}; border: 1px solid ${borderColor}; border-radius: 4px; color: ${textColor}; font-weight: 500; cursor: ${cursor}; vertical-align: middle;">🔧 ${info.name}${statusIcon}</span>`;
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
