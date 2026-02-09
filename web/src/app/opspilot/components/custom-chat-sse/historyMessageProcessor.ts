/**
 * 历史消息内容处理器
 * 用于将历史会话中的 AG-UI 协议消息解析并渲染为 HTML
 */

import { BrowserStepProgressData, BrowserStepsHistory } from '@/app/opspilot/types/global';
import { renderToolCallCard, renderErrorMessage, ToolCallInfo } from './toolCallRenderer';

const escapeNewlinesInStrings = (raw: string) => {
  let result = '';
  let inSingle = false;
  let inDouble = false;
  let escaped = false;

  for (let i = 0; i < raw.length; i += 1) {
    const ch = raw[i];

    if (escaped) {
      result += ch;
      escaped = false;
      continue;
    }

    if (ch === '\\') {
      result += ch;
      escaped = true;
      continue;
    }

    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
      result += ch;
      continue;
    }

    if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
      result += ch;
      continue;
    }

    if ((ch === '\n' || ch === '\r') && (inSingle || inDouble)) {
      result += ch === '\n' ? '\\n' : '\\r';
      continue;
    }

    result += ch;
  }

  return result;
};

const normalizePythonJson = (raw: string) => {
  const escapedRaw = escapeNewlinesInStrings(raw);
  let result = '';
  let inSingle = false;
  let inDouble = false;
  let escaped = false;
  let token = '';

  const flushToken = () => {
    if (!token) return;
    if (!inSingle && !inDouble) {
      if (token === 'None') result += 'null';
      else if (token === 'True') result += 'true';
      else if (token === 'False') result += 'false';
      else result += token;
    } else {
      result += token;
    }
    token = '';
  };

  for (let i = 0; i < escapedRaw.length; i += 1) {
    const ch = escapedRaw[i];

    if (inSingle || inDouble) {
      if (escaped) {
        result += ch;
        escaped = false;
        continue;
      }
      if (ch === '\\') {
        result += ch;
        escaped = true;
        continue;
      }
      if (inSingle && ch === "'") {
        result += '"';
        inSingle = false;
        continue;
      }
      if (inDouble && ch === '"') {
        result += '"';
        inDouble = false;
        continue;
      }
      if (ch === '\n') {
        result += '\\n';
        continue;
      }
      if (ch === '\r') {
        result += '\\r';
        continue;
      }
      if (inSingle && ch === '"') {
        result += '\\"';
        continue;
      }
      result += ch;
      continue;
    }

    if (ch === "'") {
      flushToken();
      inSingle = true;
      result += '"';
      continue;
    }
    if (ch === '"') {
      flushToken();
      inDouble = true;
      result += '"';
      continue;
    }
    if (/[A-Za-z_]/.test(ch)) {
      token += ch;
      continue;
    }
    flushToken();
    result += ch;
  }

  flushToken();
  return result;
};

const removeTrailingCommas = (raw: string) => {
  let result = '';
  let inSingle = false;
  let inDouble = false;
  let escaped = false;

  for (let i = 0; i < raw.length; i += 1) {
    const ch = raw[i];

    if (escaped) {
      result += ch;
      escaped = false;
      continue;
    }

    if (ch === '\\') {
      result += ch;
      escaped = true;
      continue;
    }

    if (ch === "'" && !inDouble) {
      inSingle = !inSingle;
      result += ch;
      continue;
    }
    if (ch === '"' && !inSingle) {
      inDouble = !inDouble;
      result += ch;
      continue;
    }

    if (!inSingle && !inDouble && ch === ',') {
      let j = i + 1;
      while (j < raw.length && /\s/.test(raw[j])) j += 1;
      if (raw[j] === ']' || raw[j] === '}') {
        continue;
      }
    }

    result += ch;
  }

  return result;
};

const parseJsonArray = (raw: string): any[] | null => {
  const splitTopLevelObjects = (value: string) => {
    const objects: string[] = [];
    let inSingle = false;
    let inDouble = false;
    let escaped = false;
    let depth = 0;
    let startIndex = -1;

    for (let i = 0; i < value.length; i += 1) {
      const ch = value[i];

      if (escaped) {
        escaped = false;
        continue;
      }

      if (ch === '\\') {
        escaped = true;
        continue;
      }

      if (ch === "'" && !inDouble) {
        inSingle = !inSingle;
        continue;
      }

      if (ch === '"' && !inSingle) {
        inDouble = !inDouble;
        continue;
      }

      if (inSingle || inDouble) continue;

      if (ch === '{') {
        if (depth === 0) startIndex = i;
        depth += 1;
        continue;
      }

      if (ch === '}') {
        depth -= 1;
        if (depth === 0 && startIndex >= 0) {
          objects.push(value.slice(startIndex, i + 1));
          startIndex = -1;
        }
      }
    }

    return objects;
  };

  const parseObjectsLenient = (value: string) => {
    const objectSlices = splitTopLevelObjects(value);
    if (!objectSlices.length) return null;
    const parsed = objectSlices
      .map(slice => {
        const normalized = normalizePythonJson(slice);
        const cleaned = removeTrailingCommas(normalized);
        try {
          return JSON.parse(cleaned);
        } catch {
          return null;
        }
      })
      .filter(Boolean);
    return parsed.length ? (parsed as any[]) : null;
  };

  const unwrapQuoted = (value: string) => {
    let trimmed = value.trim();
    if ((trimmed.startsWith('b"') && trimmed.endsWith('"')) || (trimmed.startsWith("b'") && trimmed.endsWith("'"))) {
      trimmed = trimmed.slice(2);
    }
    if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
      try {
        const unwrapped = JSON.parse(trimmed);
        return typeof unwrapped === 'string' ? unwrapped : trimmed;
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  };

  const extractArraySlice = (value: string) => {
    const start = value.indexOf('[');
    const end = value.lastIndexOf(']');
    if (start >= 0 && end > start) {
      return value.slice(start, end + 1);
    }
    return value;
  };

  const tryParseArray = (value: string) => {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : null;
    } catch {
      return null;
    }
  };

  const unwrapped = extractArraySlice(unwrapQuoted(raw));
  const cleanedRaw = removeTrailingCommas(escapeNewlinesInStrings(unwrapped));
  const directParsed = tryParseArray(cleanedRaw);
  if (directParsed) return directParsed;

  const normalized = normalizePythonJson(unwrapped);
  const cleanedNormalized = removeTrailingCommas(normalized);
  const normalizedParsed = tryParseArray(cleanedNormalized);
  if (normalizedParsed) return normalizedParsed;

  return parseObjectsLenient(unwrapped) || parseObjectsLenient(normalized) || null;
};

const buildFromEvents = (events: any[], finalize = true) => {
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
    ? { steps: [...steps], isRunning: finalize ? false : isRunning }
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
    return buildFromEvents(content, true).content;
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

  return buildFromEvents(parsedContent, true).content;
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
    return buildFromEvents(content, true);
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

  return buildFromEvents(parsedContent, true);
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
