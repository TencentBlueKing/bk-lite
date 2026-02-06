/**
 * 历史消息内容处理器
 * 用于将历史会话中的 AG-UI 协议消息解析并渲染为 HTML
 */

import { BrowserStepProgressData, BrowserStepsHistory } from '@/app/opspilot/types/global';
import { renderToolCallCard, renderErrorMessage, ToolCallInfo } from './toolCallRenderer';

const normalizePythonJson = (raw: string) => {
  const replacedLiterals = raw
    .replace(/\bNone\b/g, 'null')
    .replace(/\bTrue\b/g, 'true')
    .replace(/\bFalse\b/g, 'false');
  return replacedLiterals.replace(/'([^'\\]*(?:\\.[^'\\]*)*)'/g, (_, value) => {
    const unescaped = value.replace(/\\'/g, "'");
    const escaped = unescaped.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    return `"${escaped}"`;
  });
};

const parseJsonArray = (raw: string): any[] | null => {
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    // ignore
  }
  try {
    const normalized = normalizePythonJson(raw);
    const parsed = JSON.parse(normalized);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

const buildFromEvents = (events: any[]) => {
  const parts: string[] = [];
  const toolCalls = new Map<string, ToolCallInfo>();
  let currentText = '';
  let lastBlockType: string | null = null;
  const steps: BrowserStepProgressData[] = [];
  let isRunning = false;
  let lastStep: BrowserStepProgressData | null = null;

  const upsertStep = (stepData: BrowserStepProgressData) => {
    const existingIndex = steps.findIndex(s => s.step_number === stepData.step_number);
    if (existingIndex >= 0) {
      steps[existingIndex] = stepData;
    } else {
      steps.push(stepData);
    }
    steps.sort((a, b) => a.step_number - b.step_number);
    lastStep = stepData;
    isRunning = true;
  };

  events.forEach((msg: any) => {
    switch (msg.type) {
      case 'TEXT_MESSAGE_CONTENT':
        currentText += msg.delta || '';
        break;

      case 'TOOL_CALL_START':
        if (currentText) {
          if (parts.length > 0 && lastBlockType !== 'text') {
            parts.push('\n\n' + currentText);
          } else {
            parts.push(currentText);
          }
          currentText = '';
          lastBlockType = 'text';
        }
        toolCalls.set(msg.toolCallId, {
          name: msg.toolCallName,
          args: '',
          status: 'completed',
          result: undefined
        });
        break;

      case 'TOOL_CALL_ARGS':
        if (msg.toolCallId) {
          const tool = toolCalls.get(msg.toolCallId);
          if (tool) {
            tool.args += msg.delta || '';
          }
        }
        break;

      case 'TOOL_CALL_RESULT':
        if (msg.toolCallId) {
          const tool = toolCalls.get(msg.toolCallId);
          if (tool) {
            tool.result = msg.content || '';
            tool.status = 'completed';
          }
        }
        break;

      case 'TOOL_CALL_END':
        if (msg.toolCallId) {
          const tool = toolCalls.get(msg.toolCallId);
          if (tool) {
            const toolCard = renderToolCallCard(msg.toolCallId, tool);
            if (parts.length > 0 && lastBlockType === 'toolCall') {
              parts.push(toolCard);
            } else if (parts.length > 0) {
              parts.push('\n\n' + toolCard);
            } else {
              parts.push(toolCard);
            }
            lastBlockType = 'toolCall';
          }
        }
        break;

      case 'RUN_ERROR':
      case 'ERROR':
        if (currentText) {
          parts.push(currentText);
          currentText = '';
        }
        const errorMessage = msg.message || '执行过程中发生错误';
        const errorHtml = renderErrorMessage(errorMessage, msg.type === 'RUN_ERROR' ? 'run_error' : 'error', msg.code);
        if (parts.length > 0) {
          parts.push('\n\n' + errorHtml);
        } else {
          parts.push(errorHtml);
        }
        lastBlockType = 'error';
        break;

      case 'CUSTOM':
        if (msg.name === 'browser_step_progress' && msg.value) {
          upsertStep(msg.value as BrowserStepProgressData);
        }
        break;

      case 'RUN_FINISHED':
        if (steps.length > 0) {
          isRunning = false;
        }
        break;

      default:
        break;
    }
  });

  if (currentText) {
    if (parts.length > 0 && lastBlockType !== 'text') {
      parts.push('\n\n' + currentText);
    } else {
      parts.push(currentText);
    }
  }

  const contentText = parts.join('');
  const browserStepsHistory: BrowserStepsHistory | null = steps.length
    ? { steps: [...steps], isRunning }
    : null;

  return {
    content: contentText,
    browserStepProgress: lastStep,
    browserStepsHistory
  };
};

/**
 * 处理历史消息中的 bot 内容
 * 解析 AG-UI 协议消息数组，渲染文本和工具调用
 * @param content 原始消息内容（可能是 JSON 字符串）
 * @param role 消息角色
 * @returns 处理后的 HTML 内容
 */
export const processHistoryMessageContent = (content: string, role: string): string => {
  // 非 bot 消息直接返回
  if (role !== 'bot') return typeof content === 'string' ? content : String(content ?? '');

  if (Array.isArray(content)) {
    return buildFromEvents(content).content;
  }

  if (typeof content !== 'string') {
    if (content === null || content === undefined) return '';
    if (typeof content === 'object') {
      try {
        return JSON.stringify(content);
      } catch {
        return String(content);
      }
    }
    return String(content);
  }

  const parsedContent = parseJsonArray(content);
  if (!parsedContent) return content;

  return buildFromEvents(parsedContent).content;
};

export const processHistoryMessageWithExtras = (
  content: unknown,
  role: string
): {
  content: string;
  browserStepProgress?: BrowserStepProgressData | null;
  browserStepsHistory?: BrowserStepsHistory | null;
} => {
  if (role !== 'bot') {
    return {
      content: typeof content === 'string' ? content : String(content ?? ''),
      browserStepProgress: null,
      browserStepsHistory: null
    };
  }

  if (Array.isArray(content)) {
    return buildFromEvents(content);
  }

  if (typeof content !== 'string') {
    return {
      content: content === null || content === undefined ? '' : String(content),
      browserStepProgress: null,
      browserStepsHistory: null
    };
  }

  const parsedContent = parseJsonArray(content);
  if (!parsedContent) {
    return {
      content,
      browserStepProgress: null,
      browserStepsHistory: null
    };
  }

  return buildFromEvents(parsedContent);
};

/**
 * 批量处理历史消息列表
 * @param messages 原始消息数组
 * @returns 处理后的消息数组
 */
export const processHistoryMessages = (messages: any[]): any[] => {
  return messages.map(msg => ({
    ...msg,
    content: processHistoryMessageContent(msg.content, msg.role)
  }));
};
