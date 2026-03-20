/**
 * 工具调用渲染器
 * 负责生成工具调用和错误消息的 HTML
 */

import { BrowserTaskReceivedData } from '@/app/opspilot/types/global';

export interface ToolCallInfo {
  name: string;
  args: string;
  status: 'calling' | 'completed';
  result?: string;
  browserTaskReceived?: BrowserTaskReceivedData;
}

/**
 * 初始化全局工具详情交互（只执行一次）
 */
let tooltipInitialized = false;
let tooltipPanelElement: HTMLDivElement | null = null;
let activeTriggerElement: HTMLElement | null = null;
let activeToolId: string | null = null;
let positionAnimationFrameId: number | null = null;

const escapeHtml = (text: string) => {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

const formatDetailValue = (value: unknown) => {
  if (value === null || value === undefined) {
    return '';
  }

  if (typeof value === 'string') {
    return value;
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const formatBrowserTaskReceived = (data?: BrowserTaskReceivedData) => {
  if (!data) return '';

  return formatDetailValue(data.task_final);
};

const buildToolDetailSections = (info: ToolCallInfo) => {
  const sections: Array<{ title: string; content: string }> = [];

  const browserTaskContent = formatBrowserTaskReceived(info.browserTaskReceived);
  if (browserTaskContent) {
    sections.push({
      title: 'browser_task_received',
      content: browserTaskContent,
    });
  }

  if (info.result) {
    sections.push({
      title: 'result',
      content: info.result,
    });
  }

  return sections;
};

const encodeToolDetails = (info: ToolCallInfo) => {
  const detailSections = buildToolDetailSections(info);
  if (!detailSections.length) return '';

  try {
    return encodeURIComponent(JSON.stringify(detailSections));
  } catch {
    return '';
  }
};

const renderFloatingPanelContent = (detailSections: Array<{ title: string; content: string }>) => {
  if (!tooltipPanelElement) return;

  tooltipPanelElement.innerHTML = `<div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px;"><span style="font-size: 12px; font-weight: 600; color: var(--color-text-2);">工具详情</span><button type="button" class="tool-call-copy" aria-label="复制内容" title="复制内容" style="display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border-radius: 6px; border: 1px solid rgba(15, 23, 42, 0.1); background: var(--color-bg-1); color: var(--color-text-2); font-size: 14px; cursor: pointer; flex-shrink: 0;"><span class="tool-call-copy-label">⧉</span></button></div>${detailSections.map(section => `<div class="tool-call-panel-section" style="margin-top: 10px;"><div class="tool-call-panel-section-title" style="font-size: 12px; line-height: 18px; color: var(--color-text-3); margin-bottom: 6px;">${escapeHtml(section.title)}</div><pre class="tool-call-panel-section-content" style="margin: 0; padding: 10px 12px; white-space: pre-wrap; word-break: break-word; background: var(--color-fill-2); border-radius: 6px; color: var(--color-text-1); font-size: 12px; line-height: 1.6; overflow-x: auto; user-select: text;">${escapeHtml(section.content)}</pre></div>`).join('')}`;
};

export const syncActiveToolCallPanel = (toolId: string, info: ToolCallInfo) => {
  if (!tooltipInitialized || !tooltipPanelElement || activeToolId !== toolId || tooltipPanelElement.style.display !== 'block') {
    return;
  }

  const detailSections = buildToolDetailSections(info);
  if (!detailSections.length) {
    tooltipPanelElement.style.display = 'none';
    tooltipPanelElement.innerHTML = '';
    return;
  }

  renderFloatingPanelContent(detailSections);

  const nextTrigger = document.querySelector(`.tool-call-trigger[data-tool-id="${CSS.escape(toolId)}"]`) as HTMLElement | null;
  if (nextTrigger) {
    activeTriggerElement = nextTrigger;
    const rect = nextTrigger.getBoundingClientRect();
    if (rect.width > 0 || rect.height > 0) {
      let top = rect.bottom + 8;
      let left = rect.left;
      const panelRect = tooltipPanelElement.getBoundingClientRect();

      if (left + panelRect.width > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - panelRect.width - 8);
      }

      if (top + panelRect.height > window.innerHeight - 8) {
        top = Math.max(8, rect.top - panelRect.height - 8);
      }

      tooltipPanelElement.style.top = `${top}px`;
      tooltipPanelElement.style.left = `${left}px`;
    }
  }
};

export const closeActiveToolCallPanel = (toolId?: string) => {
  if (!tooltipInitialized || !tooltipPanelElement) {
    return;
  }

  if (toolId && activeToolId !== toolId) {
    return;
  }

  if (positionAnimationFrameId !== null) {
    window.cancelAnimationFrame(positionAnimationFrameId);
    positionAnimationFrameId = null;
  }

  tooltipPanelElement.style.display = 'none';
  tooltipPanelElement.innerHTML = '';

  if (activeTriggerElement) {
    activeTriggerElement.setAttribute('data-open', 'false');
    const icon = activeTriggerElement.querySelector('.tool-call-expand-icon');
    if (icon) {
      icon.textContent = '▾';
    }
  }

  activeTriggerElement = null;
  activeToolId = null;
};

const initGlobalTooltip = () => {
  if (tooltipInitialized) return;
  tooltipInitialized = true;

  tooltipPanelElement = document.createElement('div');
  tooltipPanelElement.className = 'tool-call-floating-panel';
  tooltipPanelElement.style.cssText = [
    'position: fixed',
    'display: none',
    'z-index: 10000',
    'width: min(680px, calc(100vw - 32px))',
    'max-height: min(420px, calc(100vh - 32px))',
    'overflow: auto',
    'padding: 12px',
    'background: var(--color-fill-1)',
    'border: 1px solid rgba(15, 23, 42, 0.08)',
    'border-radius: 8px',
    'box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12)',
    'user-select: text',
    'pointer-events: auto'
  ].join(';');
  document.body.appendChild(tooltipPanelElement);

  const closeAllPanels = () => {
    if (positionAnimationFrameId !== null) {
      window.cancelAnimationFrame(positionAnimationFrameId);
      positionAnimationFrameId = null;
    }

    if (tooltipPanelElement) {
      tooltipPanelElement.style.display = 'none';
      tooltipPanelElement.innerHTML = '';
    }

    if (activeTriggerElement) {
      activeTriggerElement.setAttribute('data-open', 'false');
      const icon = activeTriggerElement.querySelector('.tool-call-expand-icon');
      if (icon) {
        icon.textContent = '▾';
      }
      activeTriggerElement = null;
    }

    activeToolId = null;
  };

  const keepPanelAligned = () => {
    const trigger = syncActiveTriggerElement();
    if (trigger && tooltipPanelElement?.style.display === 'block') {
      updatePanelPosition(trigger);
      positionAnimationFrameId = window.requestAnimationFrame(keepPanelAligned);
      return;
    }

    if (positionAnimationFrameId !== null) {
      window.cancelAnimationFrame(positionAnimationFrameId);
      positionAnimationFrameId = null;
    }
  };

  const syncActiveTriggerElement = () => {
    if (!activeToolId) return null;

    if (activeTriggerElement?.isConnected) {
      return activeTriggerElement;
    }

    const nextTrigger = document.querySelector(`.tool-call-trigger[data-tool-id="${CSS.escape(activeToolId)}"]`) as HTMLElement | null;
    activeTriggerElement = nextTrigger;
    if (!nextTrigger) {
      closeAllPanels();
      return null;
    }

    nextTrigger.setAttribute('data-open', 'true');
    const icon = nextTrigger.querySelector('.tool-call-expand-icon');
    if (icon) {
      icon.textContent = '▴';
    }

    return nextTrigger;
  };

  const updatePanelPosition = (trigger: HTMLElement) => {
    if (!tooltipPanelElement) return;

    const triggerRect = trigger.getBoundingClientRect();
    const panelRect = tooltipPanelElement.getBoundingClientRect();
    const gap = 8;

    if (triggerRect.width === 0 && triggerRect.height === 0) {
      const syncedTrigger = syncActiveTriggerElement();
      if (!syncedTrigger || syncedTrigger === trigger) {
        closeAllPanels();
        return;
      }

      updatePanelPosition(syncedTrigger);
      return;
    }

    let top = triggerRect.bottom + gap;
    let left = triggerRect.left;

    if (left + panelRect.width > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - panelRect.width - 8);
    }

    if (top + panelRect.height > window.innerHeight - 8) {
      top = Math.max(8, triggerRect.top - panelRect.height - gap);
    }

    tooltipPanelElement.style.top = `${top}px`;
    tooltipPanelElement.style.left = `${left}px`;
  };

  const parseToolDetails = (encodedDetails: string) => {
    if (!encodedDetails) return [] as Array<{ title: string; content: string }>;

    try {
      const decoded = decodeURIComponent(encodedDetails);
      const parsed = JSON.parse(decoded);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  };

  const renderFloatingPanel = (trigger: HTMLElement) => {
    if (!tooltipPanelElement) return false;

    const detailSections = parseToolDetails(trigger.getAttribute('data-tool-details') || '');
    if (!detailSections.length) return false;

    renderFloatingPanelContent(detailSections);
    tooltipPanelElement.style.display = 'block';
    updatePanelPosition(trigger);
    return true;
  };

  const copyPanelContent = async (panel: HTMLElement) => {
    const sections = Array.from(panel.querySelectorAll<HTMLElement>('.tool-call-panel-section'));
    const copyText = sections
      .map((section) => {
        const title = section.querySelector<HTMLElement>('.tool-call-panel-section-title')?.textContent?.trim() || '';
        const content = section.querySelector<HTMLElement>('.tool-call-panel-section-content')?.textContent?.trim() || '';
        return title && content ? `${title}\n${content}` : content;
      })
      .filter(Boolean)
      .join('\n\n');

    if (!copyText) return false;

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(copyText);
        return true;
      }
    } catch {}

    const textarea = document.createElement('textarea');
    textarea.value = copyText;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();

    try {
      const success = document.execCommand('copy');
      document.body.removeChild(textarea);
      return success;
    } catch {
      document.body.removeChild(textarea);
      return false;
    }
  };

  document.addEventListener('click', async (e) => {
    const target = e.target as HTMLElement;
    const copyButton = target.closest('.tool-call-copy') as HTMLElement | null;

    if (copyButton) {
      e.preventDefault();
      e.stopPropagation();

      const panel = tooltipPanelElement;
      if (!panel) return;

      const copied = await copyPanelContent(panel);
      const label = copyButton.querySelector('.tool-call-copy-label');
      if (copied && label) {
        const originalText = label.textContent;
        const originalTitle = copyButton.getAttribute('title');
        const originalAriaLabel = copyButton.getAttribute('aria-label');
        label.textContent = '✓';
        copyButton.setAttribute('title', '已复制');
        copyButton.setAttribute('aria-label', '已复制');
        window.setTimeout(() => {
          label.textContent = originalText;
          if (originalTitle) {
            copyButton.setAttribute('title', originalTitle);
          }
          if (originalAriaLabel) {
            copyButton.setAttribute('aria-label', originalAriaLabel);
          }
        }, 1200);
      }
      return;
    }

    const trigger = target.closest('.tool-call-trigger') as HTMLElement | null;
    if (trigger) {
      e.preventDefault();

      const isOpen = trigger.getAttribute('data-open') === 'true';
      closeAllPanels();

      if (!isOpen) {
        const rendered = renderFloatingPanel(trigger);
        if (!rendered) return;
        trigger.setAttribute('data-open', 'true');
        activeTriggerElement = trigger;
        activeToolId = trigger.getAttribute('data-tool-id');
        if (positionAnimationFrameId !== null) {
          window.cancelAnimationFrame(positionAnimationFrameId);
        }
        positionAnimationFrameId = window.requestAnimationFrame(keepPanelAligned);
        const icon = trigger.querySelector('.tool-call-expand-icon') as HTMLElement | null;
        if (icon) {
          icon.textContent = '▴';
        }
      }
      return;
    }

    if (!target.closest('.tool-call-floating-panel')) {
      closeAllPanels();
    }
  });

  window.addEventListener('resize', () => {
    const trigger = syncActiveTriggerElement();
    if (trigger && tooltipPanelElement?.style.display === 'block') {
      updatePanelPosition(trigger);
    }
  });

  window.addEventListener('scroll', () => {
    const trigger = syncActiveTriggerElement();
    if (trigger && tooltipPanelElement?.style.display === 'block') {
      updatePanelPosition(trigger);
    }
  }, true);
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
  const detailSections = buildToolDetailSections(info);
  const hasDetails = detailSections.length > 0;
  const encodedToolDetails = hasDetails ? encodeToolDetails(info) : '';

  // 根据状态决定颜色
  const bgColor = isCalling ? 'rgba(22, 119, 255, 0.1)' : 'rgba(82, 196, 26, 0.1)';
  const borderColor = isCalling ? '#1677ff' : '#52c41a';
  const textColor = isCalling ? '#1677ff' : '#52c41a';

  // Spin 动画样式
  const spinStyle = isCalling ? '<style>@keyframes tool-spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }</style>' : '';

  // 状态图标
  const statusIcon = isCalling
    ? `<span style="display: inline-block; width: 12px; height: 12px; margin-left: 6px; border: 2px solid ${textColor}; border-top-color: transparent; border-radius: 50%; animation: tool-spin 0.8s linear infinite;"></span>`
    : `<span style="display: inline-block; margin-left: 6px; color: ${textColor};">✓</span>`;

  const expandIcon = hasDetails
    ? `<span class="tool-call-expand-icon" style="display: inline-block; margin-left: 2px; font-size: 11px; color: ${textColor};">▾</span>`
    : '';

  return `${spinStyle}<span class="tool-call-wrapper" data-tool-id="${escapeHtml(id)}" style="display: inline-block; margin-right: 8px; margin-bottom: 8px; vertical-align: top; max-width: 100%;"><button type="button" class="tool-call-trigger" data-tool-id="${escapeHtml(id)}" data-open="false" ${hasDetails ? `data-tool-details="${escapeHtml(encodedToolDetails)}"` : ''} style="display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; font-size: 13px; line-height: 20px; background: ${bgColor}; border: 1px solid ${borderColor}; border-radius: 4px; color: ${textColor}; font-weight: 500; cursor: ${hasDetails ? 'pointer' : 'default'}; vertical-align: middle; max-width: 100%;"><span>🔧 ${escapeHtml(info.name)}</span>${statusIcon}${expandIcon}</button></span>`;
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

  return `<div class="my-3 p-4 rounded-lg border-l-4 border-red-500 bg-linear-to-br from-(--color-fill-2) to-red-50/5 shadow-md">
    <div class="flex items-center gap-2 mb-2">
      <span class="text-lg">${config.icon}</span>
      <span class="flex-1 font-semibold text-sm text-red-500">${config.title}</span>
    </div>
    <div class="p-2 bg-(--color-fill-3) rounded text-xs text-(--color-text-2) font-mono">${error}</div>
  </div>`;
};
