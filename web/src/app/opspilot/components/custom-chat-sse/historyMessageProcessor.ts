/**
 * 历史消息内容处理器
 * 用于将历史会话中的 AG-UI 协议消息解析并渲染为 HTML
 */

import {
  AgentStepProgressData,
  ApprovalRequest,
  BrowserStepProgressData,
  BrowserStepsHistory,
  BrowserTaskReceivedData,
  ConfigAnalysisReport,
  ConfigDiffReport,
  RepairCommands,
  ReportFileDownload,
  UserChoiceRequest
} from '@/app/opspilot/types/global';
import {
  ApprovalRequestValue,
  ConfigAnalysisReportValue,
  ConfigDiffReportValue,
  RepairCommandsValue,
  ReportFileDownloadValue,
  UserChoiceRequestValue
} from '@/app/opspilot/types/chat';
import {
  isStructuredConfigAnalysisReport,
  normalizeConfigAnalysisRecommendations,
  normalizeConfigAnalysisSection
} from './aguiMessageHandler';
import { initToolCallTooltips, renderAllToolCalls, renderErrorMessage, ToolCallInfo } from './toolCallRenderer';

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

const parseAttachmentToolResult = (content: string) => {
  try {
    return JSON.parse(content);
  } catch {
    const extractField = (field: string) => {
      const match = content.match(new RegExp(`[\"']${field}[\"']\\s*:\\s*[\"']([^\"']+)[\"']`));
      return match?.[1];
    };

    return {
      filename: extractField('filename'),
      file_url: extractField('file_url'),
      mime_type: extractField('mime_type'),
    };
  }
};

const buildFromEvents = (events: any[], finalize = true) => {
  const parts: string[] = [];
  const toolCalls = new Map<string, ToolCallInfo>();
  const reportFileDownloads: ReportFileDownload[] = [];
  const configDiffReports: ConfigDiffReport[] = [];
  const configAnalysisReports: ConfigAnalysisReport[] = [];
  const userChoiceRequests: UserChoiceRequest[] = [];
  const approvalRequests: ApprovalRequest[] = [];
  const repairCommandsList: RepairCommands[] = [];
  // 历史回放没有真实的接收时间，用自增序号保证卡片按事件顺序排序
  let seq = 0;
  let currentText = '';
  let thinking = '';
  let isThinking = false;
  let lastBlockType: string | null = null;
  const steps: BrowserStepProgressData[] = [];
  const agentSteps: any[] = [];
  let isRunning = false;
  let lastStep: BrowserStepProgressData | null = null;
  const pendingToolIds: string[] = [];

  const flushToolCalls = () => {
    if (pendingToolIds.length > 0) {
      const group = new Map<string, ToolCallInfo>();
      pendingToolIds.forEach(id => {
        const tool = toolCalls.get(id);
        if (tool) group.set(id, tool);
      });
      const toolCallsHtml = renderAllToolCalls(group, false);
      if (toolCallsHtml) {
        if (parts.length > 0) {
          parts.push('\n\n' + toolCallsHtml);
        } else {
          parts.push(toolCallsHtml);
        }
      }
      pendingToolIds.length = 0;
      lastBlockType = 'toolCall';
    }
  };

  const flushCurrentText = () => {
    if (!currentText) return;
    flushToolCalls();
    if (parts.length > 0 && lastBlockType !== 'text') {
      parts.push('\n\n' + currentText);
    } else {
      parts.push(currentText);
    }
    currentText = '';
    lastBlockType = 'text';
  };

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

  const findLatestCallingToolCallId = (preferredToolName?: string) => {
    const entries = Array.from(toolCalls.entries()).reverse();

    if (preferredToolName) {
      const matchedEntry = entries.find(([, tool]) => tool.status === 'calling' && tool.name === preferredToolName);
      if (matchedEntry) {
        return matchedEntry[0];
      }
    }

    const latestCallingEntry = entries.find(([, tool]) => tool.status === 'calling');
    return latestCallingEntry?.[0] || null;
  };

  events.forEach((msg: any) => {
    switch (msg.type) {
      case 'RUN_STARTED':
        break;

      case 'THINKING':
        thinking += msg.delta || '';
        isThinking = true;
        break;

      case 'TEXT_MESSAGE_CONTENT':
        isThinking = false;
        // If pending tool calls exist and this is the start of new text, flush them
        if (pendingToolIds.length > 0 && !currentText) {
          flushToolCalls();
        }
        currentText += msg.delta || '';
        break;

      case 'TOOL_CALL_START':
        isThinking = false;
        flushCurrentText();
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
            if (tool.name === 'generate_attachment_file') {
              try {
                const parsed = parseAttachmentToolResult(msg.content || '{}');
                if (parsed?.file_url && parsed?.filename) {
                  reportFileDownloads.push({
                    download_id: `attachment_${msg.toolCallId}`,
                    filename: parsed.filename,
                    file_url: parsed.file_url,
                    mime_type: parsed.mime_type || 'application/octet-stream',
                    received_at: Date.now(),
                  });
                }
              } catch {
                // ignore invalid tool result payloads
              }
            }
          }
        }
        break;

      case 'TOOL_CALL_END':
        if (msg.toolCallId && toolCalls.has(msg.toolCallId)) {
          pendingToolIds.push(msg.toolCallId);
          lastBlockType = 'toolCall';
        }
        break;

      case 'RUN_ERROR':
      case 'ERROR':
        isThinking = false;
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
        isThinking = false;
        if (msg.name === 'browser_step_progress' && msg.value) {
          upsertStep(msg.value as BrowserStepProgressData);
        } else if (msg.name === 'browser_task_received' && msg.value) {
          const browserTaskReceived = msg.value as BrowserTaskReceivedData;
          const toolCallId = findLatestCallingToolCallId(typeof browserTaskReceived.tool === 'string' ? browserTaskReceived.tool : undefined);
          if (toolCallId) {
            const tool = toolCalls.get(toolCallId);
            if (tool) {
              tool.browserTaskReceived = browserTaskReceived;
            }
          }
        } else if (msg.name === 'agent_step_progress' && msg.value) {
          const data = msg.value as any;
          const key = `${data.agent_name || 'main'}_${data.step}`;
          const existingIdx = agentSteps.findIndex(
            (d: any) => `${d.agent_name || 'main'}_${d.step}` === key
          );
          if (existingIdx >= 0) {
            agentSteps[existingIdx] = data;
          } else {
            agentSteps.push(data);
          }
        } else if (msg.name === 'sub_agent_progress' && msg.value) {
          const data = msg.value as any;
          const newStep = {
            agent_name: data.agent_name,
            step: 0,
            max_steps: 0,
            status: data.status,
            description: data.description,
          };
          const existingIdx = agentSteps.findIndex(
            (d: any) => d.agent_name === data.agent_name && (d.status === 'started' || d.status === 'running')
          );
          if (existingIdx >= 0 && (data.status === 'completed' || data.status === 'error')) {
            agentSteps[existingIdx] = newStep;
          } else {
            agentSteps.push(newStep);
          }
        } else if (msg.name === 'config_diff_report' && msg.value) {
          const value = msg.value as ConfigDiffReportValue;
          flushCurrentText();
          flushToolCalls();
          configDiffReports.push({ ...value, received_at: ++seq });
          parts.push(`\n\n<!--CONFIG_DIFF:${value.report_id}-->`);
          lastBlockType = 'configDiff';
        } else if (msg.name === 'config_analysis_report' && msg.value) {
          const value = msg.value as ConfigAnalysisReportValue;
          flushCurrentText();
          flushToolCalls();
          if (isStructuredConfigAnalysisReport(value)) {
            const report: ConfigAnalysisReport = {
              ...value,
              summary: value.summary || {},
              severity_sections: value.severity_sections.map(normalizeConfigAnalysisSection),
              recommendations: normalizeConfigAnalysisRecommendations(value.recommendations),
              markdown: value.markdown,
              fallback_markdown: value.fallback_markdown || value.markdown,
              received_at: ++seq,
            };
            const existingIndex = configAnalysisReports.findIndex(r => r.report_id === value.report_id);
            if (existingIndex >= 0) {
              configAnalysisReports[existingIndex] = report;
            } else {
              configAnalysisReports.push(report);
              parts.push(`\n\n<!--CONFIG_ANALYSIS:${value.report_id}-->`);
              lastBlockType = 'configAnalysis';
            }
          } else {
            const fallbackMarkdown = value.fallback_markdown || value.markdown;
            if (fallbackMarkdown) {
              if (parts.length > 0 && lastBlockType !== 'text') {
                parts.push('\n\n' + fallbackMarkdown);
              } else {
                parts.push(fallbackMarkdown);
              }
              lastBlockType = 'text';
            }
          }
        } else if (msg.name === 'user_choice_request' && msg.value) {
          const value = msg.value as UserChoiceRequestValue;
          flushCurrentText();
          flushToolCalls();
          // 历史回放默认按超时处理（只读卡片），后续 user_choice_result 事件会修正实际状态
          userChoiceRequests.push({ ...value, received_at: 0, status: 'timeout' });
          parts.push(`\n\n<!--USER_CHOICE:${value.choice_id}-->`);
          lastBlockType = 'userChoice';
        } else if (msg.name === 'user_choice_result' && msg.value) {
          const value = msg.value as { choice_id: string; selected: string[]; source: string };
          const request = userChoiceRequests.find(r => r.choice_id === value.choice_id);
          if (request) {
            request.status = value.source === 'user' ? 'submitted' : 'timeout';
            request.selected = value.selected;
          }
        } else if (msg.name === 'approval_request' && msg.value) {
          const value = msg.value as ApprovalRequestValue;
          flushCurrentText();
          flushToolCalls();
          // received_at 置 0 使历史中的审批卡片显示为已超时的只读状态
          approvalRequests.push({ ...value, received_at: 0, status: 'pending' });
        } else if (msg.name === 'repair_commands' && msg.value) {
          const value = msg.value as RepairCommandsValue;
          flushCurrentText();
          flushToolCalls();
          repairCommandsList.push({ ...value, received_at: ++seq });
        } else if (msg.name === 'report_file_download' && msg.value) {
          const value = msg.value as ReportFileDownloadValue;
          reportFileDownloads.push({ ...value, received_at: ++seq });
        }
        break;

      case 'RUN_FINISHED':
        isThinking = false;
        if (steps.length > 0) {
          isRunning = false;
        }
        break;

      default:
        break;
    }
  });

  // 输出剩余的文本和工具调用
  flushCurrentText();
  flushToolCalls();

  // Fallback: report_config_diff 工具已完成但 CUSTOM 事件缺失时，从工具入参恢复 diff 报告
  if (configDiffReports.length === 0) {
    toolCalls.forEach((tool, toolCallId) => {
      if (tool.name !== 'report_config_diff' || !tool.args) return;
      try {
        const args = JSON.parse(tool.args);
        if (args.items && args.items.length > 0) {
          configDiffReports.push({
            report_id: `fallback_${toolCallId}`,
            title: args.title || '',
            cluster_name: args.cluster_name || '',
            items: args.items,
            received_at: ++seq,
          });
        }
      } catch {
        // args 解析失败则跳过回退
      }
    });
  }

  const contentText = parts.join('');
  const browserStepsHistory: BrowserStepsHistory | null = steps.length
    ? { steps: [...steps], isRunning: finalize ? false : isRunning }
    : null;

  return {
    content: contentText,
    thinking,
    isThinking: finalize ? false : isThinking,
    browserStepProgress: lastStep,
    browserStepsHistory,
    agentStepProgress: agentSteps.length > 0 ? agentSteps : undefined,
    reportFileDownloads: reportFileDownloads.length > 0 ? reportFileDownloads : undefined,
    configDiffReports: configDiffReports.length > 0 ? configDiffReports : undefined,
    configAnalysisReports: configAnalysisReports.length > 0 ? configAnalysisReports : undefined,
    userChoiceRequests: userChoiceRequests.length > 0 ? userChoiceRequests : undefined,
    approvalRequests: approvalRequests.length > 0 ? approvalRequests : undefined,
    repairCommands: repairCommandsList.length > 0 ? repairCommandsList : undefined,
    toolCalls: toolCalls.size > 0 ? Array.from(toolCalls.entries()).map(([id, info]) => ({
      id, name: info.name, args: info.args, status: info.status as 'calling' | 'completed', result: info.result
    })) : undefined
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
  // 确保工具调用事件处理器已初始化
  if (typeof window !== 'undefined') {
    initToolCallTooltips();
  }

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
  thinking?: string;
  isThinking?: boolean;
  browserStepProgress?: BrowserStepProgressData | null;
  browserStepsHistory?: BrowserStepsHistory | null;
  agentStepProgress?: AgentStepProgressData[];
  reportFileDownloads?: ReportFileDownload[];
  configDiffReports?: ConfigDiffReport[];
  configAnalysisReports?: ConfigAnalysisReport[];
  userChoiceRequests?: UserChoiceRequest[];
  approvalRequests?: ApprovalRequest[];
  repairCommands?: RepairCommands[];
  toolCalls?: Array<{ id: string; name: string; args: string; status: 'calling' | 'completed'; result?: string }>;
} => {
  if (role !== 'bot') {
    return {
      content: typeof content === 'string' ? content : String(content ?? ''),
      thinking: '',
      isThinking: false,
      browserStepProgress: null,
      browserStepsHistory: null,
      reportFileDownloads: undefined,
    };
  }

  if (Array.isArray(content)) {
    return buildFromEvents(content, true);
  }

  if (typeof content !== 'string') {
    return {
      content: content === null || content === undefined ? '' : String(content),
      thinking: '',
      isThinking: false,
      browserStepProgress: null,
      browserStepsHistory: null,
      reportFileDownloads: undefined,
    };
  }

  const parsedContent = parseJsonArray(content);
  if (!parsedContent) {
    return {
      content,
      thinking: '',
      isThinking: false,
      browserStepProgress: null,
      browserStepsHistory: null,
      reportFileDownloads: undefined,
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
